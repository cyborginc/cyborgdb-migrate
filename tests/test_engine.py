from __future__ import annotations

import threading
from unittest.mock import patch

from cyborgdb_migrate.engine import MigrationEngine, ProgressUpdate
from cyborgdb_migrate.models import SourceInfo, VectorRecord


def make_records(start: int, count: int, dim: int = 4) -> list[VectorRecord]:
    """Create a batch of test VectorRecords."""
    return [
        VectorRecord(
            id=f"vec-{i}",
            vector=[float(i)] * dim,
            metadata={"idx": i},
        )
        for i in range(start, start + count)
    ]


class MockSource:
    def __init__(self, batches: list[tuple[list[VectorRecord], str | None]]):
        self._batches = batches
        self.extract_calls = []

    def name(self) -> str:
        return "MockSource"

    def extract(self, index_name, batch_size=100, namespace=None, resume_from=None):
        self.extract_calls.append(
            {"index_name": index_name, "batch_size": batch_size,
             "namespace": namespace, "resume_from": resume_from}
        )
        start_idx = 0
        if resume_from is not None:
            start_idx = int(resume_from)
        for batch, cursor in self._batches[start_idx:]:
            yield batch, cursor


class MockDestination:
    def __init__(self, fail_batch: int | None = None):
        self._index_name = "test-dest"
        self._upserted: list[list[VectorRecord]] = []
        self._fail_batch = fail_batch
        self._batch_count = 0
        self._stored: dict[str, VectorRecord] = {}

    def upsert_batch(self, records):
        self._batch_count += 1
        if self._fail_batch is not None and self._batch_count == self._fail_batch:
            raise ConnectionError("Simulated upsert failure")
        self._upserted.append(records)
        for r in records:
            # Store copies so verification tests can corrupt them independently
            self._stored[r.id] = VectorRecord(
                id=r.id, vector=list(r.vector), metadata=dict(r.metadata), contents=r.contents
            )
        return len(records)

    def get_count(self):
        return len(self._stored)

    def fetch_by_ids(self, ids):
        return [self._stored[id] for id in ids if id in self._stored]


def make_source_info(count: int = 200) -> SourceInfo:
    return SourceInfo(
        source_type="mock",
        index_or_collection_name="test-index",
        dimension=4,
        vector_count=count,
    )


class TestMigrationEngineHappyPath:
    def test_basic_migration(self):
        batches = [
            (make_records(0, 5), "1"),
            (make_records(5, 5), "2"),
        ]
        source = MockSource(batches)
        dest = MockDestination()

        engine = MigrationEngine(
            source=source,
            destination=dest,
            source_info=make_source_info(10),
            batch_size=5,
            checkpoint_every=100,  # don't checkpoint during test
            spot_check_per_batch=2,
        )
        result = engine.run()

        assert result.vectors_migrated == 10
        assert result.vectors_expected == 10
        assert len(dest._upserted) == 2
        assert result.spot_check_passed is True

    def test_empty_source(self):
        source = MockSource([])
        dest = MockDestination()

        engine = MigrationEngine(
            source=source,
            destination=dest,
            source_info=make_source_info(0),
            batch_size=5,
        )
        result = engine.run()

        assert result.vectors_migrated == 0
        assert len(dest._upserted) == 0


class TestMigrationEngineCancellation:
    def test_cancel_stops_migration(self):
        batches = [
            (make_records(0, 5), "1"),
            (make_records(5, 5), "2"),
            (make_records(10, 5), "3"),
        ]
        source = MockSource(batches)
        dest = MockDestination()
        cancel = threading.Event()

        engine = MigrationEngine(
            source=source,
            destination=dest,
            source_info=make_source_info(15),
            batch_size=5,
            checkpoint_every=100,
            cancel_event=cancel,
        )

        # Cancel after first batch is submitted
        original_upsert = dest.upsert_batch

        def cancelling_upsert(records):
            result = original_upsert(records)
            cancel.set()
            return result

        dest.upsert_batch = cancelling_upsert

        with patch("cyborgdb_migrate.engine.save_checkpoint"):
            result = engine.run()

        assert result.spot_check_details == "Migration was cancelled"


class TestMigrationEngineRetry:
    def test_retry_on_transient_error(self):
        batches = [(make_records(0, 3), "1")]
        source = MockSource(batches)
        dest = MockDestination()

        call_count = 0
        original_upsert = dest.upsert_batch

        def failing_upsert(records):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("transient")
            return original_upsert(records)

        dest.upsert_batch = failing_upsert

        engine = MigrationEngine(
            source=source,
            destination=dest,
            source_info=make_source_info(3),
            batch_size=3,
        )

        with patch("cyborgdb_migrate.engine.time.sleep"):
            result = engine.run()

        assert result.vectors_migrated == 3
        assert call_count == 2  # 1 fail + 1 success


class TestMigrationEngineCheckpoint:
    def test_checkpoint_resume(self):
        batches = [
            (make_records(0, 5), "1"),
            (make_records(5, 5), "2"),
        ]
        source = MockSource(batches)
        dest = MockDestination()

        engine = MigrationEngine(
            source=source,
            destination=dest,
            source_info=make_source_info(10),
            batch_size=5,
        )

        # Mock loading checkpoint
        from cyborgdb_migrate.checkpoint import CheckpointData

        cp = CheckpointData(
            source_type="mock",
            source_index="test-index",
            dest_index="test-dest",
            cursor="1",
            vectors_migrated=5,
            batches_completed=1,
        )

        with patch("cyborgdb_migrate.engine.load_checkpoint", return_value=cp):
            engine.run(resume=True)

        # Should have resumed from cursor "1"
        assert source.extract_calls[0]["resume_from"] == "1"


class TestMigrationEngineVerification:
    def test_verification_pass(self):
        batches = [(make_records(0, 4), "1")]
        source = MockSource(batches)
        dest = MockDestination()

        engine = MigrationEngine(
            source=source,
            destination=dest,
            source_info=make_source_info(4),
            batch_size=4,
            spot_check_per_batch=4,
        )
        result = engine.run()
        assert result.spot_check_passed is True
        assert "4/4 verified" in result.spot_check_details

    def test_verification_fail_vector_mismatch(self):
        batches = [(make_records(0, 4), "1")]
        source = MockSource(batches)
        dest = MockDestination()

        engine = MigrationEngine(
            source=source,
            destination=dest,
            source_info=make_source_info(4),
            batch_size=4,
            spot_check_per_batch=4,
        )
        engine.run()

        # Corrupt a stored vector
        for rec in dest._stored.values():
            rec.vector = [999.0] * 4
            break

        # Re-verify
        passed, details = engine.verify()
        assert not passed
        assert "3/4 verified" in details


class TestMigrationEngineSampling:
    def test_samples_cached_from_every_batch(self):
        batches = [
            (make_records(0, 10), "1"),
            (make_records(10, 10), "2"),
            (make_records(20, 10), "3"),
        ]
        source = MockSource(batches)
        dest = MockDestination()

        engine = MigrationEngine(
            source=source,
            destination=dest,
            source_info=make_source_info(30),
            batch_size=10,
            spot_check_per_batch=4,
        )
        engine.run()

        # 4 samples per batch * 3 batches = 12 samples
        assert len(engine._verification_samples) == 12


class TestMigrationEngineProgress:
    def test_progress_callbacks(self):
        batches = [(make_records(0, 5), "1")]
        source = MockSource(batches)
        dest = MockDestination()
        updates = []

        engine = MigrationEngine(
            source=source,
            destination=dest,
            source_info=make_source_info(5),
            batch_size=5,
            on_progress=lambda u: updates.append(u),
        )
        engine.run()

        assert len(updates) > 0
        assert all(isinstance(u, ProgressUpdate) for u in updates)
        # Last update should show vectors migrated
        final = updates[-1]
        assert final.vectors_migrated == 5
