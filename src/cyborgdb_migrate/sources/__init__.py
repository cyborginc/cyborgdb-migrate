from cyborgdb_migrate.sources.pinecone import PineconeSource
from cyborgdb_migrate.sources.qdrant import QdrantSource
from cyborgdb_migrate.sources.weaviate import WeaviateSource
from cyborgdb_migrate.sources.chromadb import ChromaDBSource
from cyborgdb_migrate.sources.milvus import MilvusSource

SOURCE_REGISTRY: dict[str, type] = {
    "Pinecone": PineconeSource,
    "Qdrant": QdrantSource,
    "Weaviate": WeaviateSource,
    "ChromaDB": ChromaDBSource,
    "Milvus": MilvusSource,
}
