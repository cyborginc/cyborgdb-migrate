from __future__ import annotations

import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from cyborgdb_migrate.checkpoint import (
    CheckpointData,
    delete_checkpoint,
    load_checkpoint,
    save_checkpoint,
)
from cyborgdb_migrate.destination import CyborgDestination
from cyborgdb_migrate.models import MigrationResult, SourceInfo, VectorRecord
from cyborgdb_migrate.sources.base import SourceConnector

logger = logging.getLogger(__name__)


@dataclass
class ProgressUpdate:
    """Progress information passed to UI callbacks."""

    vectors_migrated: int
    vectors_total: int
    batches_completed: int
    batches_total: int
    errors: int
    elapsed_seconds: float
    speed_vectors_per_sec: float
    message: str = ""


class MigrationEngine:
    """Core migration engine with double-buffered extraction/upsert."""

    def __init__(
        self,
        source: SourceConnector,
        destination: CyborgDestination,
        source_info: SourceInfo,
        batch_size: int = 100,
        checkpoint_every: int = 10,
        spot_check_per_batch: int = 4,
        on_progress: Callable[[ProgressUpdate], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self.source = source
        self.destination = destination
        self.source_info = source_info
        self.batch_size = batch_size
        self.checkpoint_every = checkpoint_every
        self.spot_check_per_batch = spot_check_per_batch
        self.on_progress = on_progress
        self.cancel_event = cancel_event or threading.Event()
        self._verification_samples: list[VectorRecord] = []

    def run(
        self,
        namespace: str | None = None,
        resume: bool = False,
    ) -> MigrationResult:
        """Execute the migration with double-buffered extraction/upsert."""
        start_time = time.monotonic()
        vectors_migrated = 0
        batches_completed = 0
        errors = 0
        resume_cursor: str | None = None

        source_type = self.source_info.source_type
        source_index = self.source_info.index_or_collection_name
        dest_index = self.destination._index_name or ""

        # Check for existing checkpoint
        if resume:
            cp = load_checkpoint(source_type, source_index, dest_index)
            if cp is not None:
                resume_cursor = cp.cursor
                vectors_migrated = cp.vectors_migrated
                batches_completed = cp.batches_completed
                logger.info(
                    "Resuming from checkpoint: %d vectors, %d batches, cursor=%s",
                    vectors_migrated,
                    batches_completed,
                    resume_cursor,
                )

        total_vectors = self.source_info.vector_count
        total_batches = max(1, (total_vectors + self.batch_size - 1) // self.batch_size)

        self._emit_progress(
            vectors_migrated, total_vectors, batches_completed, total_batches, errors, start_time,
            message="Starting migration..." if not resume_cursor else "Resuming migration...",
        )

        # Double-buffered upsert using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending_future = None

            for batch, cursor in self.source.extract(
                index_name=source_index,
                batch_size=self.batch_size,
                namespace=namespace,
                resume_from=resume_cursor,
            ):
                # Check cancellation
                if self.cancel_event.is_set():
                    # Wait for pending upsert to finish
                    if pending_future is not None:
                        pending_future.result()
                    self._save_checkpoint(
                        source_type, source_index, dest_index, namespace,
                        cursor, vectors_migrated, total_vectors,
                        batches_completed, start_time,
                    )
                    logger.info("Migration cancelled at %d vectors", vectors_migrated)
                    break

                # Cache samples for verification
                self._cache_samples(batch)

                # Wait for previous upsert to complete
                if pending_future is not None:
                    try:
                        count = pending_future.result()
                        vectors_migrated += count
                        batches_completed += 1
                    except Exception as e:
                        errors += 1
                        logger.error("Batch upsert failed: %s", e)
                        batches_completed += 1

                # Submit current batch for upsert
                pending_future = executor.submit(self._upsert_with_retry, batch)

                # Checkpoint
                if batches_completed > 0 and batches_completed % self.checkpoint_every == 0:
                    self._save_checkpoint(
                        source_type, source_index, dest_index, namespace,
                        cursor, vectors_migrated, total_vectors,
                        batches_completed, start_time,
                    )
                    self._emit_progress(
                        vectors_migrated, total_vectors, batches_completed, total_batches,
                        errors, start_time, message=f"Checkpoint saved ({batches_completed} batches)",
                    )
                else:
                    self._emit_progress(
                        vectors_migrated, total_vectors, batches_completed, total_batches,
                        errors, start_time,
                        message=f"Batch {batches_completed} sent ({len(batch)} vec)",
                    )

            # Wait for final upsert
            if pending_future is not None:
                try:
                    count = pending_future.result()
                    vectors_migrated += count
                    batches_completed += 1
                except Exception as e:
                    errors += 1
                    logger.error("Final batch upsert failed: %s", e)
                    batches_completed += 1

        elapsed = time.monotonic() - start_time

        self._emit_progress(
            vectors_migrated, total_vectors, batches_completed, total_batches,
            errors, start_time, message="Migration complete, verifying...",
        )

        # Verify
        if not self.cancel_event.is_set():
            spot_passed, spot_details = self.verify()
            # Clean up checkpoint on success
            delete_checkpoint(source_type, source_index, dest_index)
        else:
            spot_passed = False
            spot_details = "Migration was cancelled"

        return MigrationResult(
            vectors_migrated=vectors_migrated,
            vectors_expected=total_vectors,
            duration_seconds=elapsed,
            spot_check_passed=spot_passed,
            spot_check_details=spot_details,
            index_name=dest_index,
            key_file_path=None,
        )

    def verify(self) -> tuple[bool, str]:
        """Verify migration integrity using cached samples."""
        issues = []

        # Count check
        try:
            dest_count = self.destination.get_count()
            expected = self.source_info.vector_count
            if dest_count < expected:
                issues.append(
                    f"Count mismatch: destination has {dest_count}, expected {expected}"
                )
            count_msg = f"{dest_count:,}/{expected:,} vectors"
        except Exception as e:
            issues.append(f"Count check failed: {e}")
            count_msg = "count check failed"

        # Spot check using cached samples
        if not self._verification_samples:
            details = f"Count check: {count_msg}. No samples cached for spot check."
            return len(issues) == 0, details

        sample_ids = [s.id for s in self._verification_samples]
        try:
            fetched = self.destination.fetch_by_ids(sample_ids)
        except Exception as e:
            issues.append(f"Spot check fetch failed: {e}")
            details = f"Count check: {count_msg}. Spot check fetch failed: {e}"
            return False, details

        fetched_map = {r.id: r for r in fetched}
        checked = 0
        mismatches = 0
        for sample in self._verification_samples:
            dest_rec = fetched_map.get(sample.id)
            if dest_rec is None:
                mismatches += 1
                continue
            checked += 1

            # Vector comparison — flatten to 1-D to avoid shape mismatches
            src_vec = np.asarray(sample.vector, dtype=np.float32).ravel()
            dst_vec = np.asarray(dest_rec.vector, dtype=np.float32).ravel()
            if src_vec.shape != dst_vec.shape or not np.allclose(src_vec, dst_vec, atol=1e-6):
                mismatches += 1
                continue

            # Metadata comparison
            if sample.metadata != dest_rec.metadata:
                mismatches += 1

        total_samples = len(self._verification_samples)
        passed_count = total_samples - mismatches
        spot_msg = f"{passed_count}/{total_samples} verified"

        if mismatches > 0:
            issues.append(f"Spot check: {mismatches}/{total_samples} mismatched")

        details = f"Count check: {count_msg}. Spot check: {spot_msg}"
        return len(issues) == 0, details

    def _upsert_with_retry(self, batch: list[VectorRecord]) -> int:
        """Upsert with exponential backoff retry."""
        delays = [1, 2, 4]
        last_error = None
        for attempt in range(len(delays) + 1):
            try:
                return self.destination.upsert_batch(batch)
            except Exception as e:
                last_error = e
                if attempt < len(delays):
                    delay = delays[attempt]
                    logger.warning(
                        "Upsert retry %d/%d after %ds: %s",
                        attempt + 1, len(delays), delay, e,
                    )
                    time.sleep(delay)
        # Final failure — log and continue
        ids = [r.id for r in batch[:5]]
        logger.error(
            "Batch upsert failed after %d retries (sample IDs: %s): %s",
            len(delays), ids, last_error,
        )
        raise last_error  # type: ignore[misc]

    def _cache_samples(self, batch: list[VectorRecord]) -> None:
        """Cache random samples from a batch for verification."""
        if not batch:
            return
        k = min(self.spot_check_per_batch, len(batch))
        samples = random.sample(batch, k)
        self._verification_samples.extend(samples)

    def _save_checkpoint(
        self,
        source_type: str,
        source_index: str,
        dest_index: str,
        namespace: str | None,
        cursor: str | None,
        vectors_migrated: int,
        vectors_total: int,
        batches_completed: int,
        start_time: float,
    ) -> None:
        cp = CheckpointData(
            source_type=source_type,
            source_index=source_index,
            dest_index=dest_index,
            namespace=namespace,
            cursor=cursor,
            vectors_migrated=vectors_migrated,
            vectors_total=vectors_total,
            batch_size=self.batch_size,
            batches_completed=batches_completed,
        )
        save_checkpoint(cp)
        logger.info("Checkpoint saved: %d vectors, %d batches", vectors_migrated, batches_completed)

    def _emit_progress(
        self,
        vectors_migrated: int,
        vectors_total: int,
        batches_completed: int,
        batches_total: int,
        errors: int,
        start_time: float,
        message: str = "",
    ) -> None:
        if self.on_progress is None:
            return
        elapsed = time.monotonic() - start_time
        speed = vectors_migrated / elapsed if elapsed > 0 else 0
        self.on_progress(
            ProgressUpdate(
                vectors_migrated=vectors_migrated,
                vectors_total=vectors_total,
                batches_completed=batches_completed,
                batches_total=batches_total,
                errors=errors,
                elapsed_seconds=elapsed,
                speed_vectors_per_sec=speed,
                message=message,
            )
        )
