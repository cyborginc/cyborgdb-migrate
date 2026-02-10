from __future__ import annotations

import logging
from typing import Iterator

from cyborgdb_migrate.models import SourceInfo, VectorRecord
from cyborgdb_migrate.sources.base import CredentialField, SourceConnector

logger = logging.getLogger(__name__)


class ChromaDBSource(SourceConnector):
    def __init__(self) -> None:
        self._mode: str = "remote"
        self._path: str = "./chroma_data"
        self._host: str = "localhost"
        self._port: int = 8000
        self._client = None

    def name(self) -> str:
        return "ChromaDB"

    def credential_fields(self) -> list[CredentialField]:
        return [
            CredentialField(
                key="mode",
                label="Mode",
                default="remote",
                help_text="'local' for PersistentClient with a filesystem path, "
                "'remote' for HttpClient",
            ),
            CredentialField(
                key="path",
                label="Data Path",
                default="./chroma_data",
                help_text="Filesystem path to ChromaDB data directory",
                visible_when={"mode": "local"},
            ),
            CredentialField(
                key="host",
                label="Host",
                default="localhost",
                visible_when={"mode": "remote"},
            ),
            CredentialField(
                key="port",
                label="Port",
                default="8000",
                visible_when={"mode": "remote"},
            ),
        ]

    def configure(self, credentials: dict[str, str]) -> None:
        self._mode = credentials.get("mode", "remote").strip()
        if self._mode not in ("local", "remote"):
            raise ValueError(f"ChromaDB mode must be 'local' or 'remote', got '{self._mode}'")

        if self._mode == "local":
            self._path = credentials.get("path", "./chroma_data").strip()
            if not self._path:
                raise ValueError("ChromaDB data path is required in local mode")
        else:
            self._host = credentials.get("host", "localhost").strip()
            port_str = credentials.get("port", "8000").strip()
            try:
                self._port = int(port_str)
            except ValueError:
                raise ValueError(f"Invalid port number: {port_str}")

    def connect(self) -> None:
        import chromadb

        if self._mode == "local":
            self._client = chromadb.PersistentClient(path=self._path)
            logger.info("Connected to ChromaDB (local) at %s", self._path)
        else:
            self._client = chromadb.HttpClient(host=self._host, port=self._port)
            logger.info("Connected to ChromaDB (remote) at %s:%d", self._host, self._port)

        # Validate connection
        self._client.heartbeat()

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
