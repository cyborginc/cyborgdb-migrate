# Contributing to cyborgdb-migrate

Thanks for your interest in contributing!

## Development Setup

1. Clone the repo:

```bash
git clone https://github.com/cyborginc/cyborgdb-migrate.git
cd cyborgdb-migrate
```

2. Create a virtual environment and install dev dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,all]"
```

3. Run the tests:

```bash
pytest
```

4. Lint with ruff:

```bash
ruff check src/ tests/
```

## Local Source Databases

The `scripts/seed/` directory contains a Docker Compose setup for running source databases locally:

```bash
docker compose -f scripts/seed/docker-compose.yml up -d
```

This starts ChromaDB, Qdrant, Weaviate, Milvus, and a local CyborgDB instance.

## Project Structure

```
src/cyborgdb_migrate/
  cli.py              # Entry point (argparse + headless mode)
  app.py              # Textual TUI application
  config.py           # TOML config loader
  engine.py           # Migration engine (double-buffered extraction/upsert)
  destination.py      # CyborgDB destination handler
  checkpoint.py       # Checkpoint save/load/delete
  models.py           # Data models (VectorRecord, SourceInfo, etc.)
  clipboard.py        # Cross-platform clipboard utility
  sources/            # Source connectors (one file per database)
  screens/            # TUI screens (one file per wizard step)
  widgets/            # Shared TUI widgets
```

## Adding a New Source Connector

1. Create `src/cyborgdb_migrate/sources/yoursource.py`
2. Subclass `SourceConnector` from `sources/base.py`
3. Implement all abstract methods: `name()`, `credential_fields()`, `configure()`, `connect()`, `list_indexes()`, `inspect()`, `extract()`
4. Register it in `sources/__init__.py` by adding to `SOURCE_REGISTRY`
5. Add the client library as an optional dependency in `pyproject.toml`
6. Add tests in `tests/sources/test_yoursource.py`

## Pull Requests

- Keep PRs focused — one feature or fix per PR
- Add tests for new functionality
- Run `ruff check` and `pytest` before submitting
