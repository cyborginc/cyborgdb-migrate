from __future__ import annotations

import logging
from typing import Any, Iterator

from cyborgdb_migrate.models import SourceInfo, VectorRecord
from cyborgdb_migrate.sources.base import CredentialField, SourceConnector

logger = logging.getLogger(__name__)

# Heuristic field names that suggest document content
CONTENT_FIELD_NAMES = {"content", "contents", "document", "documents", "text", "doc"}


class MilvusSource(SourceConnector):
    def __init__(self) -> None:
        self._uri: str = "http://localhost:19530"
        self._token: str | None = None
        self._database: str = "default"
        self._client = None

    def name(self) -> str:
        return "Milvus"

    def credential_fields(self) -> list[CredentialField]:
        return [
            CredentialField(key="uri", label="URI", default="http://localhost:19530"),
            CredentialField(
                key="token",
                label="Token (optional for Zilliz Cloud)",
                is_secret=True,
                required=False,
            ),
            CredentialField(key="database", label="Database", default="default"),
        ]

    def configure(self, credentials: dict[str, str]) -> None:
        self._uri = credentials.get("uri", "http://localhost:19530").strip()
        if not self._uri:
            raise ValueError("Milvus URI is required")
        token = credentials.get("token", "").strip()
        self._token = token if token else None
        self._database = credentials.get("database", "default").strip()

    def connect(self) -> None:
        from pymilvus import MilvusClient

        kwargs: dict[str, Any] = {"uri": self._uri}
        if self._token:
            kwargs["token"] = self._token
        if self._database:
            kwargs["db_name"] = self._database
        self._client = MilvusClient(**kwargs)
        # Validate connection
        self._client.list_collections()
        logger.info("Connected to Milvus at %s", self._uri)

    def list_indexes(self) -> list[str]:
        return self._client.list_collections()

    def inspect(self, index_name: str) -> SourceInfo:
        desc = self._client.describe_collection(index_name)

        # Find vector field and primary key
        dimension = 0
        pk_field = None
        vector_field = None
        metadata_fields = []
        content_field = None

        for field_info in desc.get("fields", []):
            field_name = field_info.get("name", "")
            field_type = field_info.get("type")

            # Check if this is a DataType by value or by type enum
            type_val = field_type if isinstance(field_type, int) else getattr(field_type, "value", field_type)

            if field_info.get("is_primary", False):
                pk_field = field_name

            # FLOAT_VECTOR = 101 in pymilvus DataType enum
            if type_val == 101:
                vector_field = field_name
                params = field_info.get("params", {})
                dimension = int(params.get("dim", 0))
            elif field_name not in ("pk", "id") and not field_info.get("is_primary", False):
                metadata_fields.append(field_name)
                # VARCHAR content heuristic
                if type_val == 21:  # VARCHAR
                    if field_name.lower() in CONTENT_FIELD_NAMES:
                        content_field = field_name
                    elif content_field is None:
                        max_len = int(field_info.get("params", {}).get("max_length", 0))
                        if max_len > 256:
                            content_field = field_name

        # Get vector count
        stats = self._client.get_collection_stats(index_name)
        vector_count = int(stats.get("row_count", 0))

        # Check for partitions
        partitions = self._client.list_partitions(index_name)
        namespaces = None
        if partitions and len(partitions) > 1:
            # Filter out default partition "_default"
            named = [p for p in partitions if p != "_default"]
            if named:
                namespaces = partitions

        # Try to get metric from index info
        metric = None
        index_info = self._client.list_indexes(index_name)
        if index_info:
            try:
                idx_desc = self._client.describe_index(index_name, index_info[0])
                metric_type = idx_desc.get("metric_type", "").lower()
                metric_map = {"l2": "euclidean", "ip": "dotproduct", "cosine": "cosine"}
                metric = metric_map.get(metric_type, metric_type or None)
            except Exception:
                pass

        return SourceInfo(
            source_type="milvus",
            index_or_collection_name=index_name,
            dimension=dimension,
            vector_count=vector_count,
            metric=metric,
            namespaces=namespaces,
            metadata_fields=metadata_fields,
            extra={
                "pk_field": pk_field,
                "vector_field": vector_field,
                "content_field": content_field,
            },
        )

    def extract(
        self,
        index_name: str,
        batch_size: int = 100,
        namespace: str | None = None,
        resume_from: str | None = None,
    ) -> Iterator[tuple[list[VectorRecord], str | None]]:
        # Re-inspect to get field names
        info = self.inspect(index_name)
        pk_field = info.extra.get("pk_field", "id")
        vector_field = info.extra.get("vector_field", "vector")
        content_field = info.extra.get("content_field")
        metadata_field_names = info.metadata_fields

        # Build output fields list
        output_fields = [pk_field, vector_field] + metadata_field_names

        # Use offset-based query
        offset = int(resume_from) if resume_from else 0

        partition_names = [namespace] if namespace else None

        while True:
            query_kwargs: dict[str, Any] = {
                "collection_name": index_name,
                "filter": "",
                "output_fields": output_fields,
                "limit": batch_size,
            }
            if partition_names:
                query_kwargs["partition_names"] = partition_names

            results = self._client.query(**query_kwargs, offset=offset)

            if not results:
                break

            batch = []
            for row in results:
                vec_id = str(row.get(pk_field, ""))
                vector = row.get(vector_field, [])
                if hasattr(vector, "tolist"):
                    vector = vector.tolist()

                metadata = {}
                contents = None
                for mf in metadata_field_names:
                    val = row.get(mf)
                    if val is not None:
                        if mf == content_field:
                            contents = val
                        else:
                            metadata[mf] = val

                batch.append(
                    VectorRecord(
                        id=vec_id,
                        vector=list(vector),
                        metadata=metadata,
                        contents=contents,
                    )
                )

            offset += len(results)
            cursor = str(offset)
            yield batch, cursor

            if len(results) < batch_size:
                break
