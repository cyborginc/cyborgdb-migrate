"""Seed Milvus with SIFT-128 vectors."""

from pymilvus import MilvusClient, DataType


def seed(dataset, args):
    uri = args.milvus_uri
    collection_name = args.collection_name or "sift_128"

    print(f"Connecting to Milvus at {uri}")
    client = MilvusClient(uri=uri)

    # Drop if exists
    if client.has_collection(collection_name):
        client.drop_collection(collection_name)
        print(f"Dropped existing collection '{collection_name}'")

    # Create schema
    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=20)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dataset.dimension)
    schema.add_field("category", DataType.VARCHAR, max_length=20)
    schema.add_field("seq", DataType.INT64)
    schema.add_field("content", DataType.VARCHAR, max_length=200)

    # Create index params
    index_params = client.prepare_index_params()
    index_params.add_index(field_name="vector", index_type="IVF_FLAT", metric_type="L2", params={"nlist": 128})

    client.create_collection(
        collection_name=collection_name,
        schema=schema,
        index_params=index_params,
    )
    print(f"Created collection '{collection_name}' with IVF_FLAT index")

    batch_size = 1000
    inserted = 0
    for ids, vectors, metadatas, contents in dataset.batched(batch_size):
        data = [
            {
                "id": ids[i],
                "vector": vectors[i].tolist(),
                "category": metadatas[i]["category"],
                "seq": metadatas[i]["seq"],
                "content": contents[i],
            }
            for i in range(len(ids))
        ]
        client.insert(collection_name=collection_name, data=data)
        inserted += len(ids)
        print(f"  Inserted {inserted}/{dataset.num_vectors}", end="\r")

    client.flush(collection_name=collection_name)
    stats = client.get_collection_stats(collection_name=collection_name)
    count = stats.get("row_count", inserted)
    print(f"\nDone. Collection '{collection_name}' has {count} vectors.")
