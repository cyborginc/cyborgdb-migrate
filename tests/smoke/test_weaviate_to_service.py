"""End-to-end smoke: seed Weaviate, run migrate headless, verify destination."""

from __future__ import annotations

import numpy as np
import pytest

from ._helpers import assert_index_present, run_migrate, write_migrate_config

pytest.importorskip("weaviate")
import weaviate  # noqa: E402
from weaviate.classes.config import Configure  # noqa: E402

DIM = 128
N_VECTORS = 100
# Weaviate collection names are GraphQL classes — must start uppercase.
COLLECTION_NAME = "SmokeSource"
DEST_INDEX_NAME = "smoke-dest-weaviate"


@pytest.fixture
def seeded_weaviate(smoke_stack):
    client = weaviate.connect_to_custom(
        http_host=smoke_stack["weaviate_host"],
        http_port=smoke_stack["weaviate_http_port"],
        http_secure=False,
        grpc_host=smoke_stack["weaviate_host"],
        grpc_port=smoke_stack["weaviate_grpc_port"],
        grpc_secure=False,
    )
    try:
        if client.collections.exists(COLLECTION_NAME):
            client.collections.delete(COLLECTION_NAME)
        collection = client.collections.create(
            COLLECTION_NAME,
            vector_index_config=Configure.VectorIndex.hnsw(),
        )
        rng = np.random.default_rng(seed=42)
        with collection.batch.dynamic() as batch:
            for i in range(N_VECTORS):
                batch.add_object(
                    properties={"src_idx": i, "bucket": "even" if i % 2 == 0 else "odd"},
                    vector=rng.normal(size=DIM).astype("float32").tolist(),
                )
        yield {"count": N_VECTORS}
    finally:
        client.close()


def test_weaviate_round_trip_to_cyborgdb_service(smoke_stack, seeded_weaviate, tmp_path):
    config_path = write_migrate_config(
        tmp_path,
        f"""\
        [source]
        type = "weaviate"
        host = "http://{smoke_stack["weaviate_host"]}:{smoke_stack["weaviate_http_port"]}"
        index = "{COLLECTION_NAME}"
        """,
        smoke_stack["service_url"],
        DEST_INDEX_NAME,
    )
    run_migrate(config_path, tmp_path)
    assert_index_present(smoke_stack["service_url"], DEST_INDEX_NAME)
