from __future__ import annotations

import base64
import logging
import os
import stat
from pathlib import Path
from typing import Any

import numpy as np
from cyborgdb import Client, IndexIVFFlat, IndexIVFPQ

from cyborgdb_migrate.models import VectorRecord

logger = logging.getLogger(__name__)

KEY_DIR = "./cyborgdb-migrate-keys"


def compute_n_lists(vector_count: int) -> int:
    """Derive n_lists from vector count using PRD lookup table."""
    if vector_count < 1_000:
        return 32
    if vector_count < 10_000:
        return 128
    if vector_count < 100_000:
        return 512
    if vector_count < 1_000_000:
        return 1_024
    return 4_096


class CyborgDestination:
    """Wraps CyborgDB operations for the migration tool."""

    def __init__(self) -> None:
        self._client = None
        self._index = None
        self._index_name: str | None = None
        self._last_generated_key: bytes | None = None

    def connect(self, host: str, api_key: str) -> None:
        """Connect and verify health."""

        self._host = host
        self._client = Client(base_url=host, api_key=api_key)
        self._client.get_health()
        logger.info("Connected to CyborgDB at %s", host)

    def list_indexes(self) -> list[str]:
        """List existing index names."""
        return self._client.list_indexes()

    def create_index(
        self,
        name: str,
        dimension: int,
        index_type: str,
        index_key: bytes,
        n_lists: int = 1024,
        metric: str | None = None,
    ) -> None:
        """Create a new encrypted index."""

        index_type_lower = index_type.lower()
        if index_type_lower in ("ivfflat", "ivf"):
            config = IndexIVFFlat(dimension=dimension)
        elif index_type_lower == "ivfpq":
            n_subquantizers = max(8, dimension // 8)
            config = IndexIVFPQ(dimension=dimension, pq_dim=n_subquantizers, pq_bits=8)
        else:
            raise ValueError(f"Unknown index type: {index_type}")

        kwargs: dict[str, Any] = {
            "index_name": name,
            "index_key": index_key,
            "index_config": config,
        }
        if metric:
            kwargs["metric"] = metric

        self._index = self._client.create_index(**kwargs)
        self._index_name = name
        logger.info("Created index '%s' (type=%s, dim=%d)", name, index_type, dimension)

    def load_index(self, name: str, index_key: bytes) -> None:
        """Load an existing index."""
        self._index = self._client.load_index(index_name=name, index_key=index_key)
        self._index_name = name
        logger.info("Loaded index '%s'", name)

    def get_index_dimension(self) -> int | None:
        """Return the dimension of the loaded index, or None if unavailable."""
        try:
            config = self._index.index_config
            return config.get("dimension")
        except Exception:
            return None

    def upsert_batch(self, records: list[VectorRecord]) -> int:
        """Upsert a batch of records. Returns upserted count."""
        if not records:
            return 0

        items: list[dict[str, Any]] = []
        for r in records:
            item: dict[str, Any] = {
                "id": r.id,
                "vector": np.array(r.vector, dtype=np.float32),
            }
            if r.metadata:
                item["metadata"] = r.metadata
            if r.contents is not None:
                item["contents"] = r.contents
            items.append(item)

        self._index.upsert(items)
        return len(records)

    def get_count(self) -> int:
        """Get total vector count in the loaded index."""
        return len(self._index.list_ids())

    def fetch_by_ids(self, ids: list[str]) -> list[VectorRecord]:
        """Fetch vectors by ID for spot-check verification."""
        results = self._index.get(ids=ids, include=["vector", "contents", "metadata"])
        records = []
        for item in results:
            records.append(
                VectorRecord(
                    id=item["id"],
                    vector=item.get("vector", []),
                    metadata=item.get("metadata") or {},
                    contents=item.get("contents"),
                )
            )
        return records

    def generate_and_save_key(self, key_path: str | None = None, index_name: str | None = None) -> tuple[bytes, str]:
        """Generate a new key, save to file with chmod 600.

        Returns (key_bytes, file_path). Raises FileExistsError if key file already exists.
        """

        key = Client.generate_key(save=False)
        self._last_generated_key = key

        name = index_name or self._index_name or "index"
        if key_path is None:
            key_path = os.path.join(KEY_DIR, f"{name}.key")

        path = Path(key_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.exists():
            raise FileExistsError(f"Key file already exists: {path}")

        path.write_text(base64.b64encode(key).decode("ascii"))
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 600

        logger.info("Encryption key saved to %s (base64)", path)
        return key, str(path)
