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
| `api_key` | Yes | CyborgDB service API key, sent as `X-API-Key`: the service root key or a per-user `cdbk_` token (not the `CYBORGDB_API_KEY` license key) |
| `index_name` | Yes | Destination index name |
| `create_index` | No | `true` (default) to create a new index, `false` to use existing |
| `kms_name` | No | Named KMS registry slot (e.g. `aws-kms`). When set on a new index, the service generates and wraps the key; combining it with `index_key`/`key_file` on create is an error. When set on an existing KMS-backed index, no key is required to load it. |
| `embedding_model` | No | Embedding model name registered on the CyborgDB server |
| `storage_precision` | No | Stored vector precision (`fp32` default, `fp16`) |
| `index_key` | No | Hex-encoded encryption key. On create, the index is created under this key; on an existing index, used to load it. |
| `key_file` | No | Path to an encryption key file. If it exists, the key is read from it (create and load). On create, when no key is supplied, the generated key is written here. |

### Index key handling on create

When `create_index = true` and no `kms_name` is set:

- `index_key` set → the index is created under that key; nothing is generated.
- `key_file` set and the file exists → the key is read from it and used.
- Otherwise a key is generated and saved as hex with mode `0600` to `key_file` if set, else to `./cyborgdb-migrate-checkpoints/<index_name>.key`. This happens with `--quiet` too, so unattended runs never lose the key. An existing file at the target path is never overwritten — the run aborts instead.

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
