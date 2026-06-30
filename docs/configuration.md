# Configuration Guide

Full reference for `cyborgdb-migrate` configuration, CLI options, and exit codes.

## TOML Configuration

When running in headless mode (`--config`), provide a TOML file with the sections below. Environment variables can be referenced as `${VAR_NAME}` anywhere in the config.

See [`example-config.toml`](https://github.com/cyborginc/cyborgdb-migrate/blob/main/example-config.toml) for a complete example.

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
| `kms_name` | No | Named KMS registry slot (e.g. `aws-kms`). When set on a new index, the service generates and wraps the key; no `index_key` is supplied. When set on an existing KMS-backed index, no key is required to load it. |
| `embedding_model` | No | Embedding model name registered on the CyborgDB server |
| `storage_precision` | No | Stored vector precision (`fp32` default, `fp16`) |
| `index_key` | No | Hex-encoded encryption key (for existing non-KMS indexes) |
| `key_file` | No | Path to encryption key file (for existing non-KMS indexes) |

> **Note:** CyborgDB now uses a single index type (DiskIVF). The legacy `index_type` field (`ivfflat`/`ivfpq`) is ignored with a deprecation warning.

### `[options]`

| Key | Default | Description |
|-----|---------|-------------|
| `batch_size` | `100` | Vectors per batch |
| `checkpoint_every` | `10` | Save checkpoint every N batches |
| `spot_check_per_batch` | `4` | Vectors sampled per batch for verification |

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

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Configuration or connection error |
| `2` | Migration completed but spot-check verification failed |
