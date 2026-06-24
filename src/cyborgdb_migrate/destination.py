from __future__ import annotations

import logging
from typing import Any

import numpy as np
from cyborgdb import Client

from cyborgdb_migrate.models import VectorRecord

logger = logging.getLogger(__name__)


class CyborgDestination:
    """Wraps CyborgDB operations for the migration tool."""

    def __init__(self) -> None:
        self._client = None
        self._index = None
        self._index_name: str | None = None

    def connect(self, host: str, api_key: str) -> None:
        """Connect and verify health."""

        self._host = host
        self._api_key = api_key
        self._client = Client(base_url=host, api_key=api_key)
        self._client.get_health()
        logger.info("Connected to CyborgDB at %s", host)

    def list_indexes(self) -> list[str]:
        """List existing index names."""
        if self._client is None:
            raise RuntimeError("Not connected — call connect() first")
        return self._client.list_indexes()

    def create_index(
        self,
        name: str,
        dimension: int,
        index_key: bytes | None = None,
        kms_name: str | None = None,
        metric: str | None = None,
        embedding_model: str | None = None,
        storage_precision: str | None = None,
    ) -> None:
        """Create a new encrypted DiskIVF index.

        Provide exactly one of ``index_key`` or ``kms_name``.
        """
        if self._client is None:
            raise RuntimeError("Not connected — call connect() first")
        if index_key is None and kms_name is None:
            raise ValueError("create_index requires index_key or kms_name")

        kwargs: dict[str, Any] = {
            "index_name": name,
            "dimension": dimension,
        }
        if index_key is not None:
            kwargs["index_key"] = index_key
        if kms_name is not None:
            kwargs["kms_name"] = kms_name
        if metric:
            kwargs["metric"] = metric
        if embedding_model:
            kwargs["embedding_model"] = embedding_model
        if storage_precision:
            kwargs["storage_precision"] = storage_precision

        self._index = self._client.create_index(**kwargs)
        self._index_name = name
        logger.info("Created index '%s' (dim=%d)", name, dimension)

    def load_index(self, name: str, index_key: bytes | None = None) -> None:
        """Load an existing index. ``index_key`` is required for non-KMS indexes."""
        if self._client is None:
            raise RuntimeError("Not connected — call connect() first")
        kwargs: dict[str, Any] = {"index_name": name}
        if index_key is not None:
            kwargs["index_key"] = index_key
        self._index = self._client.load_index(**kwargs)
        self._index_name = name
        logger.info("Loaded index '%s'", name)

    def get_index_dimension(self) -> int | None:
        """Return the dimension of the loaded index, or None if unavailable."""
        if self._index is None:
            return None
        try:
            config = self._index.index_config
            return config.get("dimension")
        except Exception:
            logger.debug("Failed to read index dimension", exc_info=True)
            return None

    def upsert_batch(self, records: list[VectorRecord]) -> int:
        """Upsert a batch of records. Returns upserted count."""
        if not records:
            return 0
        if self._index is None:
            raise RuntimeError("No index loaded — call create_index() or load_index() first")

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
        if self._index is None:
            raise RuntimeError("No index loaded — call create_index() or load_index() first")
        return len(self._index.list_ids())

    def fetch_by_ids(self, ids: list[str]) -> list[VectorRecord]:
        """Fetch vectors by ID for spot-check verification."""
        if self._index is None:
            raise RuntimeError("No index loaded — call create_index() or load_index() first")
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
