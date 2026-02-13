from __future__ import annotations

import logging
from typing import Iterator

from cyborgdb_migrate.models import SourceInfo, VectorRecord
from cyborgdb_migrate.sources.base import CredentialField, SourceConnector

logger = logging.getLogger(__name__)


class _ChromaDBBase(SourceConnector):
    """Shared inspect/extract logic for ChromaDB sources."""

    def __init__(self) -> None:
        self._client = None

    def list_indexes(self) -> list[str]:
        collections = self._client.list_collections()
        return [c if isinstance(c, str) else c.name for c in collections]

    def inspect(self, index_name: str) -> SourceInfo:
        collection = self._client.get_collection(index_name)
        vector_count = collection.count()

        # Get dimension by sampling one vector
        dimension = 0
        if vector_count > 0:
            sample = collection.get(limit=1, include=["embeddings"])
            if sample["embeddings"] and len(sample["embeddings"]) > 0:
                dimension = len(sample["embeddings"][0])

        return SourceInfo(
            source_type="chromadb",
            index_or_collection_name=index_name,
            dimension=dimension,
            vector_count=vector_count,
            metric="cosine",  # ChromaDB default
            namespaces=None,
        )

    def extract(
        self,
        index_name: str,
        batch_size: int = 100,
        namespace: str | None = None,
        resume_from: str | None = None,
    ) -> Iterator[tuple[list[VectorRecord], str | None]]:
        collection = self._client.get_collection(index_name)
        offset = int(resume_from) if resume_from else 0

        while True:
            result = collection.get(
                include=["embeddings", "metadatas", "documents"],
                offset=offset,
                limit=batch_size,
            )

            ids = result["ids"]
            if not ids:
                break

            embeddings = result.get("embeddings") or []
            metadatas = result.get("metadatas") or []
            documents = result.get("documents") or []

            batch = []
            for i, vec_id in enumerate(ids):
                vector = list(embeddings[i]) if i < len(embeddings) and embeddings[i] else []
                metadata = dict(metadatas[i]) if i < len(metadatas) and metadatas[i] else {}
                contents = documents[i] if i < len(documents) else None

                batch.append(
                    VectorRecord(
                        id=vec_id,
                        vector=vector,
                        metadata=metadata,
                        contents=contents,
                    )
                )

            offset += len(ids)
            cursor = str(offset)
            yield batch, cursor

            if len(ids) < batch_size:
                break


class ChromaDBLocalSource(_ChromaDBBase):
    """ChromaDB with PersistentClient (local filesystem)."""

    def __init__(self) -> None:
        super().__init__()
        self._path: str = "./chroma_data"

    def name(self) -> str:
        return "ChromaDB (Local)"

    def credential_fields(self) -> list[CredentialField]:
        return [
            CredentialField(
                key="path",
                label="Data Path",
                default="./chroma_data",
                help_text="Filesystem path to ChromaDB data directory",
            ),
        ]

    def configure(self, credentials: dict[str, str]) -> None:
        self._path = credentials.get("path", "./chroma_data").strip()
        if not self._path:
            raise ValueError("ChromaDB data path is required")

    def connect(self) -> None:
        import chromadb

        self._client = chromadb.PersistentClient(path=self._path)
        logger.info("Connected to ChromaDB (local) at %s", self._path)
        self._client.heartbeat()


class ChromaDBRemoteSource(_ChromaDBBase):
    """ChromaDB with HttpClient (remote server)."""

    def __init__(self) -> None:
        super().__init__()
        self._host: str = "localhost"
        self._port: int = 8000

    def name(self) -> str:
        return "ChromaDB (Remote)"

    def credential_fields(self) -> list[CredentialField]:
        return [
            CredentialField(
                key="host",
                label="Host",
                default="localhost",
            ),
            CredentialField(
                key="port",
                label="Port",
                default="8000",
            ),
        ]

    def configure(self, credentials: dict[str, str]) -> None:
        self._host = credentials.get("host", "localhost").strip()
        port_str = credentials.get("port", "8000").strip()
        try:
            self._port = int(port_str)
        except ValueError:
            raise ValueError(f"Invalid port number: {port_str}")

    def connect(self) -> None:
        import chromadb

        self._client = chromadb.HttpClient(host=self._host, port=self._port)
        logger.info("Connected to ChromaDB (remote) at %s:%d", self._host, self._port)
        self._client.heartbeat()
