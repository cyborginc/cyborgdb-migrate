# cyborgdb-migrate

![PyPI - Version](https://img.shields.io/pypi/v/cyborgdb-migrate)
![PyPI - License](https://img.shields.io/pypi/l/cyborgdb-migrate)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/cyborgdb-migrate)

A TUI wizard and CLI for migrating vector data from popular vector databases into [CyborgDB](https://docs.cyborg.co) — the encrypted vector database.

Supports **Pinecone**, **Qdrant**, **Weaviate**, **ChromaDB**, and **Milvus** as sources, with encrypted-at-rest indexes, checkpoint & resume, and post-migration verification built in.

## Key Features

- **Interactive TUI** — step-by-step wizard powered by [Textual](https://textual.textualize.io/)
- **Headless CLI** — non-interactive mode for scripts and CI/CD pipelines
- **Encrypted at rest** — every index is AES-encrypted with a key you control
- **Checkpoint & resume** — automatically saves progress; resume interrupted migrations
- **Spot-check verification** — post-migration vector and metadata integrity checks
- **Double-buffered I/O** — overlaps extraction and upsert for maximum throughput

## Getting Started

To get started in minutes, check out the [CyborgDB Quickstart Guide](https://docs.cyborg.co/quickstart).

### Installation

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

### Usage

#### Interactive (TUI)

```bash
cyborgdb-migrate
```

The wizard walks you through selecting a source, entering credentials, connecting to CyborgDB, and running the migration with live progress.

#### Headless (CLI)

Create a TOML config file (see [`example-config.toml`](https://github.com/cyborginc/cyborgdb-migrate/blob/main/example-config.toml)):

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

```bash
cyborgdb-migrate --config migration.toml
```

Resume an interrupted migration:

```bash
cyborgdb-migrate --config migration.toml --resume
```

## Supported Sources

| Source | Extras | Notes |
|--------|--------|-------|
| [Pinecone](https://www.pinecone.io/) | `pinecone` | Supports namespaces |
| [Qdrant](https://qdrant.tech/) | `qdrant` | Scroll-based pagination |
| [Weaviate](https://weaviate.io/) | `weaviate` | Supports named vectors |
| [ChromaDB](https://www.trychroma.com/) | `chromadb` | Local and remote modes |
| [Milvus](https://milvus.io/) | `milvus` | Supports partitions, content field heuristic |

## Configuration Reference

For full configuration details, CLI options, and exit codes, see the [Configuration Guide](https://github.com/cyborginc/cyborgdb-migrate/blob/main/docs/configuration.md).

## Documentation

For more information on CyborgDB, see the [Cyborg Docs](https://docs.cyborg.co).

## License

The CyborgDB Migration Tool is licensed under the [MIT License](LICENSE).
