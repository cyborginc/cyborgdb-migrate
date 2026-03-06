from __future__ import annotations

import logging
from typing import Iterator

from cyborgdb_migrate.models import SourceInfo, VectorRecord
from cyborgdb_migrate.sources.base import CredentialField, SourceConnector

logger = logging.getLogger(__name__)


class WeaviateSource(SourceConnector):
    def __init__(self) -> None:
        self._host: str = "http://localhost:8080"
        self._api_key: str | None = None
        self._client = None

    def name(self) -> str:
        return "Weaviate"

    def credential_fields(self) -> list[CredentialField]:
        return [
            CredentialField(key="host", label="Weaviate Host URL", default="http://localhost:8080"),
            CredentialField(
                key="api_key",
                label="Weaviate API Key (optional)",
                is_secret=True,
                required=False,
            ),
        ]

    def configure(self, credentials: dict[str, str]) -> None:
        self._host = credentials.get("host", "http://localhost:8080").strip()
        if not self._host:
            raise ValueError("Weaviate host URL is required")
        api_key = credentials.get("api_key", "").strip()
        self._api_key = api_key if api_key else None

    def connect(self) -> None:
        import weaviate
        from weaviate.auth import AuthApiKey

        # Parse host URL
        host = self._host.rstrip("/")

        connect_kwargs = {
            "http_host": host.split("://")[-1].split(":")[0],
            "http_port": int(host.split(":")[-1]) if ":" in host.split("://")[-1] else 8080,
            "http_secure": host.startswith("https"),
            "grpc_host": host.split("://")[-1].split(":")[0],
            "grpc_port": 50051,
            "grpc_secure": host.startswith("https"),
        }

        if self._api_key:
            connect_kwargs["auth_credentials"] = AuthApiKey(api_key=self._api_key)

        self._client = weaviate.connect_to_custom(**connect_kwargs)
        logger.info("Connected to Weaviate at %s", self._host)

    def list_indexes(self) -> list[str]:
        collections = self._client.collections.list_all()
        return list(collections.keys())

    def inspect(self, index_name: str) -> SourceInfo:
        collection = self._client.collections.get(index_name)

        # Get count via aggregation
        agg = collection.aggregate.over_all(total_count=True)
        vector_count = agg.total_count or 0

        # Get dimension from config or by sampling
        config = collection.config.get()
        dimension = 0
        metric = None

        # Try to get dimension from vectorizer config
        if hasattr(config, "vector_index_config"):
            vic = config.vector_index_config
            if hasattr(vic, "distance"):
                dist = str(vic.distance).lower()
                metric_map = {"cosine": "cosine", "l2-squared": "euclidean", "dot": "dotproduct"}
                metric = metric_map.get(dist, dist)

        # Sample one vector to get dimension
        if vector_count > 0:
            for item in collection.iterator(include_vector=True):
                if item.vector:
                    if isinstance(item.vector, dict):
                        # Named vectors - use default
                        for vec in item.vector.values():
                            dimension = len(vec)
                            break
                    else:
                        dimension = len(item.vector)
                break

        metadata_fields = [p.name for p in config.properties]

        return SourceInfo(
            source_type="weaviate",
            index_or_collection_name=index_name,
            dimension=dimension,
            vector_count=vector_count,
            metric=metric,
            namespaces=None,
            metadata_fields=metadata_fields,
        )

    def extract(
        self,
        index_name: str,
        batch_size: int = 100,
        namespace: str | None = None,
        resume_from: str | None = None,
    ) -> Iterator[tuple[list[VectorRecord], str | None]]:
        collection = self._client.collections.get(index_name)

        batch = []
        cursor = None

        for item in collection.iterator(include_vector=True):
            vec_id = str(item.uuid)

            # Handle both named and unnamed vectors
            vector = []
            if item.vector:
                if isinstance(item.vector, dict):
                    for vec in item.vector.values():
                        vector = list(vec)
                        break
                else:
                    vector = list(item.vector)

            metadata = {}
            if item.properties:
                metadata = {k: v for k, v in item.properties.items()}

            batch.append(
                VectorRecord(
                    id=vec_id,
                    vector=vector,
                    metadata=metadata,
                    contents=None,
                )
            )
            cursor = vec_id

            if len(batch) >= batch_size:
                yield batch, cursor
                batch = []

        if batch:
            yield batch, cursor
