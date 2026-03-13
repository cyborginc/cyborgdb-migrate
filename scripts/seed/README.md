# Seed Scripts

Test data seeding for all supported source databases. Seeds SIFT-128 vectors with metadata so you can test `cyborgdb-migrate` end-to-end.

## Prerequisites

1. **Dataset file** — SIFT-128 HDF5 file at `cyborgdb-core/datasets/sift-128-euclidean.hdf5` (relative to repo root). Override with `--dataset-path`.

2. **Docker Compose** — starts all local databases:

```bash
docker compose up -d
```

This runs:

| Service | Port(s) | Image |
|---------|---------|-------|
| ChromaDB | 8100 | `chromadb/chroma:1.5.2` |
| Qdrant | 6333, 6334 | `qdrant/qdrant:v1.17.0` |
| Weaviate | 8080, 50051 | `semitechnologies/weaviate:1.36.0` |
| Milvus | 19530 | `milvusdb/milvus:v2.5.27` |
| CyborgDB | 8000 | `cyborginc/cyborgdb:0.15.0` |

Milvus also starts etcd (port 2379) and MinIO (ports 9000, 9001) as dependencies.

CyborgDB requires `CYBORGDB_API_KEY` env var to be set.

3. **Python dependencies:**

```bash
pip install -r requirements.txt
```

## Usage

```bash
python seed.py <target> [options]
```

### Targets

| Target | Database | Default Collection | Default Connection |
|--------|----------|-------------------|-------------------|
| `chromadb-local` | ChromaDB (persistent file) | `sift_128` | `./chroma_data/` |
| `chromadb-remote` | ChromaDB (HTTP server) | `sift_128` | `localhost:8100` |
| `milvus` | Milvus | `sift_128` | `http://localhost:19530` |
| `pinecone` | Pinecone (cloud) | `sift-128` | Requires API key |
| `qdrant` | Qdrant | `sift_128` | `http://localhost:6333` |
| `weaviate` | Weaviate | `Sift128` | `localhost:8080` |
| `all` | All of the above | — | — |

### Common Options

| Flag | Default | Description |
|------|---------|-------------|
| `-n, --num-vectors` | `10000` | Number of vectors to seed |
| `--dataset-path` | `cyborgdb-core/datasets/sift-128-euclidean.hdf5` | Path to HDF5 file |
| `--collection-name` | *(per-target default)* | Override collection/index name |

### Target-Specific Options

```bash
# Milvus
--milvus-uri URI              # default: http://localhost:19530

# Pinecone (cloud — requires API key)
--pinecone-api-key KEY        # required

# Weaviate
--weaviate-host HOST          # default: localhost
--weaviate-port PORT          # default: 8080
--weaviate-grpc-port PORT     # default: 50051

# ChromaDB local
--chromadb-path PATH          # default: ./chroma_data

# ChromaDB remote
--chromadb-host HOST          # default: localhost
--chromadb-port PORT          # default: 8100

# Qdrant
--qdrant-host URL             # default: http://localhost:6333
```

## Examples

```bash
# Seed all local databases with 10k vectors (default)
python seed.py all

# Seed just Qdrant with 5k vectors
python seed.py qdrant -n 5000

# Seed ChromaDB remote with a custom collection name
python seed.py chromadb-remote --collection-name my_test_data

# Seed Pinecone (cloud)
python seed.py pinecone --pinecone-api-key pk-... -n 1000

# Seed Milvus at a custom host
python seed.py milvus --milvus-uri http://milvus.example.com:19530
```

## What Gets Seeded

Every target receives the same data from the SIFT-128 dataset:

- **Vectors** — 128-dimensional float32, from the SIFT benchmark dataset
- **IDs** — `vec_0000000` through `vec_0009999` (zero-padded)
- **Metadata** — `{"category": "cat_0"..."cat_9", "seq": 0...9999}`
- **Content** — `"SIFT vector 0"` through `"SIFT vector 9999"`

All targets are **idempotent** — existing collections are dropped and recreated on each run.

## After Seeding

Run `cyborgdb-migrate` to test migration from any seeded source into CyborgDB:

```bash
# Interactive
cyborgdb-migrate

# Headless (example with ChromaDB)
cyborgdb-migrate --config example-config.toml
```
