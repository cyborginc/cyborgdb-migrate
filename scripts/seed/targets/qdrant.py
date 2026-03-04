"""Seed Qdrant with SIFT-128 vectors."""

from qdrant_client import QdrantClient, models


def seed(dataset, args):
    host = args.qdrant_host
    collection_name = args.collection_name or "sift_128"

    print(f"Connecting to Qdrant at {host}")
    client = QdrantClient(url=host)

    # Drop if exists
    if client.collection_exists(collection_name):
        client.delete_collection(collection_name)
        print(f"Dropped existing collection '{collection_name}'")

    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(
            size=dataset.dimension,
            distance=models.Distance.EUCLID,
        ),
    )
    print(f"Created collection '{collection_name}'")

    batch_size = 500
    inserted = 0
    for ids, vectors, metadatas, contents in dataset.batched(batch_size):
        points = [
            models.PointStruct(
                id=i + inserted,
                vector=vectors[i].tolist(),
                payload={
                    **metadatas[i],
                    "content": contents[i],
                    "vec_id": ids[i],
                },
            )
            for i in range(len(ids))
        ]
        client.upsert(collection_name=collection_name, points=points)
        inserted += len(ids)
        print(f"  Inserted {inserted}/{dataset.num_vectors}", end="\r")

    info = client.get_collection(collection_name)
    print(f"\nDone. Collection '{collection_name}' has {info.points_count} vectors.")
