from cyborgdb_migrate.sources.chromadb import ChromaDBSource
from cyborgdb_migrate.sources.milvus import MilvusSource
from cyborgdb_migrate.sources.pinecone import PineconeSource
from cyborgdb_migrate.sources.qdrant import QdrantSource
from cyborgdb_migrate.sources.weaviate import WeaviateSource

SOURCE_REGISTRY: dict[str, type] = {
    "ChromaDB": ChromaDBSource,
    "Milvus": MilvusSource,
    "Pinecone": PineconeSource,
    "Qdrant": QdrantSource,
    "Weaviate": WeaviateSource,
}
