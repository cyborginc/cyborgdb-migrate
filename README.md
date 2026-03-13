# cyborgdb-migrate

A TUI wizard and CLI for migrating vector data from popular vector databases into [CyborgDB](https://cyborgdb.com) — the encrypted vector database.

## Features

- **Interactive TUI** — step-by-step wizard powered by [Textual](https://textual.textualize.io/)
- **Headless CLI** — non-interactive mode for scripts and CI/CD pipelines
- **5 source connectors** — Pinecone, Qdrant, Weaviate, ChromaDB, Milvus
- **Encrypted at rest** — every index is AES-encrypted with a key you control
- **Checkpoint & resume** — automatically saves progress; resume interrupted migrations
- **Spot-check verification** — post-migration vector and metadata integrity checks
- **Double-buffered I/O** — overlaps extraction and upsert for maximum throughput

## Installation

```bash
pip install cyborgdb-migrate
```

Install with support for your source database:

```bash
# Individual sources
pip install "cyborgdb-migrate[pinecone]"
pip install "cyborgdb-migrate[qdrant]"
pip install "cyborgdb-migrate[weaviate]"
pip install "cyborgdb-migrate[chromadb]"
pip install "cyborgdb-migrate[milvus]"

# All sources at once
pip install "cyborgdb-migrate[all]"
```

Optional syntax highlighting for the summary code snippet:

```bash
pip install "cyborgdb-migrate[syntax]"
```

## Quick Start

### Interactive (TUI)

```bash
cyborgdb-migrate
```

The wizard walks you through:

1. Selecting a source database
2. Entering credentials and picking an index/collection
3. Connecting to CyborgDB
4. Creating or selecting a destination index
5. Running the migration with live progress
6. Viewing verification results and a Python quickstart snippet

### Headless (CLI)

Create a TOML config file (see [`example-config.toml`](example-config.toml)):

```toml
[source]
type = "pinecone"
api_key = "${PINECONE_API_KEY}"
index = "my-index"

[destination]
host = "http://localhost:8000"
api_key = "${CYBORGDB_API_KEY}"
create_index = true
index_name = "my-cyborgdb-index"
index_type = "ivfflat"

[options]
batch_size = 200
checkpoint_every = 10
```

Run the migration:

```bash
cyborgdb-migrate --config migration.toml
```

Resume an interrupted migration:

```bash
cyborgdb-migrate --config migration.toml --resume
```

## Configuration Reference

### `[source]`

| Key | Required | Description |
|-----|----------|-------------|
| `type` | Yes | Source database: `pinecone`, `qdrant`, `weaviate`, `chromadb`, `milvus` |
| `index` | Yes | Index or collection name to migrate from |
| `namespace` | No | Namespace/partition to migrate (Pinecone, Milvus) |
| *(other keys)* | Varies | Passed as credentials to the source connector (e.g. `api_key`, `host`) |

### `[destination]`

| Key | Required | Description |
|-----|----------|-------------|
| `host` | Yes | CyborgDB server URL |
| `api_key` | Yes | CyborgDB API key |
| `index_name` | Yes | Destination index name |
| `create_index` | No | `true` (default) to create a new index, `false` to use existing |
| `index_type` | No | `ivfflat` (default) or `ivfpq` |
| `index_key` | No | Hex-encoded encryption key (for existing indexes) |
| `key_file` | No | Path to encryption key file (for existing indexes) |

### `[options]`

| Key | Default | Description |
|-----|---------|-------------|
| `batch_size` | `100` | Vectors per batch |
| `checkpoint_every` | `10` | Save checkpoint every N batches |
| `spot_check_per_batch` | `4` | Vectors sampled per batch for verification |

Environment variables can be referenced as `${VAR_NAME}` anywhere in the config.

## CLI Options

```
cyborgdb-migrate [OPTIONS]

Options:
  --config FILE       TOML config file for non-interactive mode
  --resume            Resume from checkpoint (requires --config)
  --batch-size INT    Override batch size (default: 100)
  --log-file FILE     Log file path (default: ./cyborgdb-migrate.log)
  --quiet             Minimal output (non-interactive only)
  --version           Show version and exit
```

## Supported Sources

| Source | Extras | Notes |
|--------|--------|-------|
| [Pinecone](https://www.pinecone.io/) | `pinecone` | Supports namespaces |
| [Qdrant](https://qdrant.tech/) | `qdrant` | Scroll-based pagination |
| [Weaviate](https://weaviate.io/) | `weaviate` | Supports named vectors |
| [ChromaDB](https://www.trychroma.com/) | `chromadb` | Local and remote modes |
| [Milvus](https://milvus.io/) | `milvus` | Supports partitions, content field heuristic |

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Configuration or connection error |
| `2` | Migration completed but spot-check verification failed |

## License

[MIT](LICENSE)
