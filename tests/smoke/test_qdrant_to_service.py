"""End-to-end smoke: seed Qdrant, run migrate headless, verify destination."""

from __future__ import annotations

import numpy as np
import pytest

from ._helpers import assert_index_present, run_migrate, write_migrate_config

pytest.importorskip("qdrant_client")
from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.models import Distance, PointStruct, VectorParams  # noqa: E402

DIM = 128
N_VECTORS = 100
COLLECTION_NAME = "smoke_source"
DEST_INDEX_NAME = "smoke-dest-qdrant"


@pytest.fixture
def seeded_qdrant(smoke_stack):
    client = QdrantClient(url=smoke_stack["qdrant_url"])
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)
    client.create_collection(
        COLLECTION_NAME,
        vectors_config=VectorParams(size=DIM, distance=Distance.COSINE),
    )
    rng = np.random.default_rng(seed=42)
    points = [
        PointStruct(
            id=i,
            vector=rng.normal(size=DIM).astype("float32").tolist(),
            payload={"src_idx": i, "bucket": "even" if i % 2 == 0 else "odd"},
        )
        for i in range(N_VECTORS)
    ]
    client.upsert(COLLECTION_NAME, points=points)
    return {"count": N_VECTORS}


def test_qdrant_round_trip_to_cyborgdb_service(smoke_stack, seeded_qdrant, tmp_path):
    config_path = write_migrate_config(
        tmp_path,
        f"""\
        [source]
        type = "qdrant"
        host = "{smoke_stack["qdrant_url"]}"
        index = "{COLLECTION_NAME}"
        """,
        smoke_stack["service_url"],
        DEST_INDEX_NAME,
    )
    run_migrate(config_path, tmp_path)
    assert_index_present(smoke_stack["service_url"], DEST_INDEX_NAME)
