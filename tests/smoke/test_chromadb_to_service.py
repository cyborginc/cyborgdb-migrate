"""End-to-end smoke: seed ChromaDB, run migrate headless, verify destination."""

from __future__ import annotations

import numpy as np
import pytest

from ._helpers import assert_index_present, run_migrate, write_migrate_config

pytest.importorskip("chromadb")
import chromadb  # noqa: E402

DIM = 768
N_VECTORS = 200
COLLECTION_NAME = "smoke-source"
DEST_INDEX_NAME = "smoke-dest-chromadb"


@pytest.fixture
def seeded_chromadb(smoke_stack):
    client = chromadb.HttpClient(
        host=smoke_stack["chromadb_host"], port=smoke_stack["chromadb_port"]
    )
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
    rng = np.random.default_rng(seed=42)
    vectors = rng.normal(size=(N_VECTORS, DIM)).astype("float32").tolist()
    ids = [f"v{i:04d}" for i in range(N_VECTORS)]
    metadatas = [
        {"src_idx": i, "bucket": "even" if i % 2 == 0 else "odd"} for i in range(N_VECTORS)
    ]
    documents = [f"document body {i}" for i in range(N_VECTORS)]
    collection.add(ids=ids, embeddings=vectors, metadatas=metadatas, documents=documents)
    return {"count": N_VECTORS}


def test_chromadb_round_trip_to_cyborgdb_service(smoke_stack, seeded_chromadb, tmp_path):
    config_path = write_migrate_config(
        tmp_path,
        f"""\
        [source]
        type = "chromadb"
        mode = "Remote"
        host = "{smoke_stack["chromadb_host"]}:{smoke_stack["chromadb_port"]}"
        index = "{COLLECTION_NAME}"
        """,
        smoke_stack["service_url"],
        DEST_INDEX_NAME,
    )
    run_migrate(config_path, tmp_path)
    assert_index_present(smoke_stack["service_url"], DEST_INDEX_NAME)
