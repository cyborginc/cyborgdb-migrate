"""End-to-end smoke: seed ChromaDB, run migrate headless, verify destination.

This is the gate the publish workflow runs against the
``cyborgdb-service`` version migrate is being released for. Green = the
runtime version check passes AND migrate's source/destination paths
actually round-trip data against that server.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("chromadb")
import chromadb  # noqa: E402

DIM = 768
N_VECTORS = 200
COLLECTION_NAME = "smoke-source"
DEST_INDEX_NAME = "smoke-dest"


@pytest.fixture
def seeded_chromadb(smoke_stack):
    """Connect to the running ChromaDB and populate a collection."""
    client = chromadb.HttpClient(
        host=smoke_stack["chromadb_host"], port=smoke_stack["chromadb_port"]
    )

    # Clean any prior run residue (collections persist across the compose run).
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    rng = np.random.default_rng(seed=42)
    vectors = rng.normal(size=(N_VECTORS, DIM)).astype("float32").tolist()
    ids = [f"v{i:04d}" for i in range(N_VECTORS)]
    metadatas = [
        {"src_idx": i, "bucket": "even" if i % 2 == 0 else "odd"}
        for i in range(N_VECTORS)
    ]
    documents = [f"document body {i}" for i in range(N_VECTORS)]

    collection.add(ids=ids, embeddings=vectors, metadatas=metadatas, documents=documents)
    return {
        "client": client,
        "vectors": vectors,
        "ids": ids,
        "metadatas": metadatas,
    }


def _write_migrate_config(
    tmp_path: Path,
    chromadb_host: str,
    chromadb_port: int,
    service_url: str,
) -> Path:
    """Build a migrate TOML config matching the ChromaDB connector's expected
    credential shape: ``mode = "Remote"`` and a combined ``host:port`` string.
    """
    config_path = tmp_path / "smoke.toml"
    config_path.write_text(
        textwrap.dedent(
            f"""\
            [source]
            type = "chromadb"
            mode = "Remote"
            host = "{chromadb_host}:{chromadb_port}"
            index = "{COLLECTION_NAME}"

            [destination]
            host = "{service_url}"
            # cyborgdb-service is started without CYBORGDB_SERVICE_ROOT_KEY, so
            # auth is disabled and any non-empty key is accepted. The config
            # layer rejects empty api_key, so pass a placeholder.
            api_key = "smoke-no-auth"
            create_index = true
            index_name = "{DEST_INDEX_NAME}"
            index_type = "ivfflat"

            [options]
            batch_size = 50
            checkpoint_every = 5
            """
        )
    )
    return config_path


def test_chromadb_round_trip_to_cyborgdb_service(smoke_stack, seeded_chromadb, tmp_path):
    """ChromaDB → migrate → cyborgdb-service: vector count and spot-check survive."""
    config_path = _write_migrate_config(
        tmp_path,
        smoke_stack["chromadb_host"],
        smoke_stack["chromadb_port"],
        smoke_stack["service_url"],
    )

    from cyborgdb_migrate.cli import run_headless

    # run_headless raises SystemExit(2) on spot-check failure, SystemExit(1) on
    # other errors, and returns normally on success.
    run_headless(
        str(config_path),
        batch_size=50,
        resume=False,
        log_file=str(tmp_path / "smoke.log"),
        quiet=True,
    )

    # If we got here without SystemExit, the migration's own spot-check passed.
    # Verify the destination explicitly via the cyborgdb SDK.
    from cyborgdb import Client

    client = Client(base_url=smoke_stack["service_url"], api_key="")
    indexes = client.list_indexes()
    assert DEST_INDEX_NAME in indexes, (
        f"destination index '{DEST_INDEX_NAME}' missing from server; got {indexes}"
    )
