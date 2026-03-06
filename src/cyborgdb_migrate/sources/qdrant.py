from __future__ import annotations

import logging
from typing import Iterator

from cyborgdb_migrate.models import SourceInfo, VectorRecord
from cyborgdb_migrate.sources.base import CredentialField, SourceConnector

logger = logging.getLogger(__name__)


class QdrantSource(SourceConnector):
    def __init__(self) -> None:
        self._host: str = "http://localhost:6333"
        self._api_key: str | None = None
        self._client = None

    def name(self) -> str:
        return "Qdrant"

    def credential_fields(self) -> list[CredentialField]:
        return [
            CredentialField(key="host", label="Qdrant Host URL", default="http://localhost:6333"),
            CredentialField(
                key="api_key",
                label="Qdrant API Key (optional)",
                is_secret=True,
                required=False,
            ),
        ]

    def configure(self, credentials: dict[str, str]) -> None:
        self._host = credentials.get("host", "http://localhost:6333").strip()
        if not self._host:
            raise ValueError("Qdrant host URL is required")
        api_key = credentials.get("api_key", "").strip()
        self._api_key = api_key if api_key else None

    def connect(self) -> None:
        from qdrant_client import QdrantClient

        kwargs = {"url": self._host}
        if self._api_key:
            kwargs["api_key"] = self._api_key
        self._client = QdrantClient(**kwargs)
        # Validate connection
        self._client.get_collections()
        logger.info("Connected to Qdrant at %s", self._host)

    def list_indexes(self) -> list[str]:
        collections = self._client.get_collections()
        return [c.name for c in collections.collections]

    def inspect(self, index_name: str) -> SourceInfo:
        info = self._client.get_collection(index_name)

        dimension = info.config.params.vectors.size
        vector_count = info.points_count or 0

        # Map Qdrant distance to standard metric names
        distance = str(info.config.params.vectors.distance).lower()
        metric_map = {"cosine": "cosine", "euclid": "euclidean", "dot": "dotproduct"}
        metric = metric_map.get(distance, distance)

        return SourceInfo(
            source_type="qdrant",
            index_or_collection_name=index_name,
            dimension=dimension,
            vector_count=vector_count,
            metric=metric,
            namespaces=None,
        )

    def extract(
        self,
        index_name: str,
        batch_size: int = 100,
        namespace: str | None = None,
        resume_from: str | None = None,
    ) -> Iterator[tuple[list[VectorRecord], str | None]]:
        offset = resume_from if resume_from else None

        while True:
            scroll_kwargs = {
                "collection_name": index_name,
                "limit": batch_size,
                "with_vectors": True,
                "with_payload": True,
            }
            if offset is not None:
                scroll_kwargs["offset"] = offset

            records, next_offset = self._client.scroll(**scroll_kwargs)

            if not records:
                break

            batch = []
            for rec in records:
                batch.append(
                    VectorRecord(
                        id=str(rec.id),
                        vector=list(rec.vector),
                        metadata=dict(rec.payload) if rec.payload else {},
                        contents=None,
                    )
                )

            cursor = str(next_offset) if next_offset is not None else None
            yield batch, cursor

            if next_offset is None:
                break
            offset = next_offset
