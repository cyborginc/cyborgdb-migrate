from cyborgdb_migrate.sources.pinecone import PineconeSource
from cyborgdb_migrate.sources.qdrant import QdrantSource
from cyborgdb_migrate.sources.weaviate import WeaviateSource
from cyborgdb_migrate.sources.chromadb import ChromaDBLocalSource, ChromaDBRemoteSource
from cyborgdb_migrate.sources.milvus import MilvusSource

SOURCE_REGISTRY: dict[str, type] = {
    "Pinecone": PineconeSource,
    "Qdrant": QdrantSource,
    "Weaviate": WeaviateSource,
    "ChromaDB (Local)": ChromaDBLocalSource,
    "ChromaDB (Remote)": ChromaDBRemoteSource,
    "Milvus": MilvusSource,
}
