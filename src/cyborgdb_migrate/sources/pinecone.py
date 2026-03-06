from __future__ import annotations

import logging
from typing import Iterator

from cyborgdb_migrate.models import SourceInfo, VectorRecord
from cyborgdb_migrate.sources.base import CredentialField, SourceConnector

logger = logging.getLogger(__name__)


class PineconeSource(SourceConnector):
    def __init__(self) -> None:
        self._api_key: str = ""
        self._client = None

    def name(self) -> str:
        return "Pinecone"

    def credential_fields(self) -> list[CredentialField]:
        return [
            CredentialField(key="api_key", label="Pinecone API Key", is_secret=True),
        ]

    def configure(self, credentials: dict[str, str]) -> None:
        api_key = credentials.get("api_key", "").strip()
        if not api_key:
            raise ValueError("Pinecone API Key is required")
        self._api_key = api_key

    def connect(self) -> None:
        from pinecone import Pinecone

        self._client = Pinecone(api_key=self._api_key)
        # Validate connection by listing indexes
        self._client.list_indexes()
        logger.info("Connected to Pinecone")

    def list_indexes(self) -> list[str]:
        indexes = self._client.list_indexes()
        return [idx.name for idx in indexes]

    def inspect(self, index_name: str) -> SourceInfo:
        index = self._client.Index(index_name)
        stats = index.describe_index_stats()

        dimension = stats.dimension
        total_count = stats.total_vector_count

        # Extract namespaces
        namespaces = None
        if stats.namespaces:
            namespaces = list(stats.namespaces.keys())

        return SourceInfo(
            source_type="pinecone",
            index_or_collection_name=index_name,
            dimension=dimension,
            vector_count=total_count,
            metric=None,  # Pinecone doesn't expose metric in stats
            namespaces=namespaces,
            extra={"namespace_counts": {
                ns: info.vector_count for ns, info in (stats.namespaces or {}).items()
            }},
        )

    def extract(
        self,
        index_name: str,
        batch_size: int = 100,
        namespace: str | None = None,
        resume_from: str | None = None,
    ) -> Iterator[tuple[list[VectorRecord], str | None]]:
        index = self._client.Index(index_name)
        ns = namespace or ""

        # Use list() to paginate through IDs, then fetch vectors
        list_kwargs = {"namespace": ns}
        if resume_from:
            list_kwargs["pagination_token"] = resume_from

        while True:
            page = index.list(**list_kwargs)

            if not page.vectors:
                break

            ids = page.vectors

            # Fetch in chunks of up to 1000 (Pinecone limit)
            all_records = []
            for i in range(0, len(ids), 1000):
                chunk_ids = ids[i : i + 1000]
                fetch_result = index.fetch(ids=chunk_ids, namespace=ns)
                for vec_id, vec_data in fetch_result.vectors.items():
                    all_records.append(
                        VectorRecord(
                            id=vec_id,
                            vector=vec_data.values,
                            metadata=dict(vec_data.metadata) if vec_data.metadata else {},
                            contents=None,
                        )
                    )

            # Yield in batch_size chunks
            pagination_token = getattr(page, "pagination", {})
            if isinstance(pagination_token, dict):
                pagination_token = pagination_token.get("next")
            else:
                pagination_token = getattr(pagination_token, "next", None)

            cursor = pagination_token

            for i in range(0, len(all_records), batch_size):
                chunk = all_records[i : i + batch_size]
                # Only use the actual cursor on the last chunk of this page
                chunk_cursor = cursor if i + batch_size >= len(all_records) else None
                yield chunk, chunk_cursor

            if not cursor:
                break
            list_kwargs["pagination_token"] = cursor
