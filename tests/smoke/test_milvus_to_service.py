"""End-to-end smoke: seed Milvus, run migrate headless, verify destination."""

from __future__ import annotations

import numpy as np
import pytest

from ._helpers import assert_index_present, run_migrate, write_migrate_config

pytest.importorskip("pymilvus")
from pymilvus import DataType, MilvusClient  # noqa: E402

DIM = 128
N_VECTORS = 100
COLLECTION_NAME = "smoke_source"
DEST_INDEX_NAME = "smoke-dest-milvus"


@pytest.fixture
def seeded_milvus(smoke_stack):
    client = MilvusClient(uri=smoke_stack["milvus_uri"])
    if client.has_collection(COLLECTION_NAME):
        client.drop_collection(COLLECTION_NAME)

    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=DIM)
    schema.add_field("src_idx", DataType.INT64)
    client.create_collection(COLLECTION_NAME, schema=schema)

    index_params = client.prepare_index_params()
    index_params.add_index(field_name="vector", index_type="AUTOINDEX", metric_type="COSINE")
    client.create_index(COLLECTION_NAME, index_params)
    client.load_collection(COLLECTION_NAME)

    rng = np.random.default_rng(seed=42)
    rows = [
        {"id": i, "vector": rng.normal(size=DIM).astype("float32").tolist(), "src_idx": i}
        for i in range(N_VECTORS)
    ]
    client.insert(COLLECTION_NAME, rows)
    client.flush(COLLECTION_NAME)
    return {"count": N_VECTORS}


def test_milvus_round_trip_to_cyborgdb_service(smoke_stack, seeded_milvus, tmp_path):
    config_path = write_migrate_config(
        tmp_path,
        f"""\
        [source]
        type = "milvus"
        uri = "{smoke_stack["milvus_uri"]}"
        index = "{COLLECTION_NAME}"
        """,
        smoke_stack["service_url"],
        DEST_INDEX_NAME,
    )
    run_migrate(config_path, tmp_path)
    assert_index_present(smoke_stack["service_url"], DEST_INDEX_NAME)
