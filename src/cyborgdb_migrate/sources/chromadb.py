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
            if sample["embeddings"] is not None and len(sample["embeddings"]) > 0:
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

            embeddings = result.get("embeddings")
            if embeddings is None:
                embeddings = []
            metadatas = result.get("metadatas")
            if metadatas is None:
                metadatas = []
            documents = result.get("documents")
            if documents is None:
                documents = []

            batch = []
            for i, vec_id in enumerate(ids):
                has_emb = i < len(embeddings) and embeddings[i] is not None
                vector = list(embeddings[i]) if has_emb else []
                has_meta = i < len(metadatas) and metadatas[i] is not None
                metadata = dict(metadatas[i]) if has_meta else {}
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


class ChromaDBSource(_ChromaDBBase):
    """ChromaDB source — supports both local (PersistentClient) and remote (HttpClient)."""

    def __init__(self) -> None:
        super().__init__()
        self._mode: str | None = None
        self._host: str = "localhost"
        self._port: int = 8100
        self._path: str = ""

    def name(self) -> str:
        return "ChromaDB"

    def credential_fields(self) -> list[CredentialField]:
        return [
            CredentialField(
                key="mode",
                label="Connection mode",
                options=["Remote", "Local"],
                default="Remote",
            ),
            CredentialField(
                key="host",
                label="ChromaDB Host:Port",
                default="localhost:8100",
                visible_when={"mode": "Remote"},
            ),
            CredentialField(
                key="path",
                label="ChromaDB Persistence Path",
                default="",
                visible_when={"mode": "Local"},
            ),
        ]

    def configure(self, credentials: dict[str, str]) -> None:
        mode = credentials.get("mode", "Remote")

        if mode == "Remote":
            self._mode = "remote"
            host_raw = credentials.get("host", "localhost:8100").strip()
            if not host_raw:
                raise ValueError("ChromaDB host is required")
            if ":" in host_raw:
                host_part, port_part = host_raw.rsplit(":", 1)
                self._host = host_part
                try:
                    self._port = int(port_part)
                except ValueError:
                    raise ValueError(f"Invalid port number: {port_part}")
            else:
                self._host = host_raw
                self._port = 8100
        else:
            self._mode = "local"
            self._path = credentials.get("path", "").strip()
            if not self._path:
                raise ValueError("ChromaDB persistence path is required")

    def connect(self) -> None:
        import chromadb

        if self._mode == "remote":
            self._client = chromadb.HttpClient(host=self._host, port=self._port)
            logger.info("Connected to ChromaDB (remote) at %s:%d", self._host, self._port)
        else:
            self._client = chromadb.PersistentClient(path=self._path)
            logger.info("Connected to ChromaDB (local) at %s", self._path)
        self._client.heartbeat()
