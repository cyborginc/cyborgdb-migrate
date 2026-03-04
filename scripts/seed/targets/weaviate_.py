"""Seed Weaviate with SIFT-128 vectors."""

from uuid import NAMESPACE_DNS, uuid5

import weaviate
from weaviate.classes.config import Configure, Property, DataType, VectorDistances


def seed(dataset, args):
    host = args.weaviate_host
    port = args.weaviate_port
    grpc_port = args.weaviate_grpc_port
    collection_name = args.collection_name or "Sift128"

    print(f"Connecting to Weaviate at {host}:{port} (gRPC: {grpc_port})")
    client = weaviate.connect_to_local(host=host, port=port, grpc_port=grpc_port)

    try:
        # Drop if exists
        if client.collections.exists(collection_name):
            client.collections.delete(collection_name)
            print(f"Dropped existing collection '{collection_name}'")

        collection = client.collections.create(
            name=collection_name,
            vectorizer_config=Configure.Vectorizer.none(),
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.L2_SQUARED,
            ),
            properties=[
                Property(name="category", data_type=DataType.TEXT),
                Property(name="seq", data_type=DataType.INT),
                Property(name="content", data_type=DataType.TEXT),
                Property(name="vec_id", data_type=DataType.TEXT),
            ],
        )
        print(f"Created collection '{collection_name}'")

        batch_size = 500
        inserted = 0
        for ids, vectors, metadatas, contents in dataset.batched(batch_size):
            with collection.batch.fixed_size(batch_size=batch_size) as batch:
                for i in range(len(ids)):
                    batch.add_object(
                        uuid=uuid5(NAMESPACE_DNS, ids[i]),
                        vector=vectors[i].tolist(),
                        properties={
                            "category": metadatas[i]["category"],
                            "seq": metadatas[i]["seq"],
                            "content": contents[i],
                            "vec_id": ids[i],
                        },
                    )
            inserted += len(ids)
            print(f"  Inserted {inserted}/{dataset.num_vectors}", end="\r")

        total = collection.aggregate.over_all(total_count=True).total_count
        print(f"\nDone. Collection '{collection_name}' has {total} vectors.")
    finally:
        client.close()
