"""Seed Pinecone with SIFT-128 vectors."""

import time

from pinecone import Pinecone, ServerlessSpec


def seed(dataset, args):
    api_key = args.pinecone_api_key
    if not api_key:
        raise ValueError("--pinecone-api-key is required for the pinecone target")

    collection_name = args.collection_name or "sift-128"

    print("Connecting to Pinecone")
    pc = Pinecone(api_key=api_key)

    # Drop if exists
    existing = [idx.name for idx in pc.list_indexes()]
    if collection_name in existing:
        pc.delete_index(collection_name)
        print(f"Dropped existing index '{collection_name}'")
        # Wait for deletion to complete
        while collection_name in [idx.name for idx in pc.list_indexes()]:
            time.sleep(1)

    pc.create_index(
        name=collection_name,
        dimension=dataset.dimension,
        metric="euclidean",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )
    print(f"Created index '{collection_name}', waiting for it to be ready...")

    # Poll until ready
    while True:
        desc = pc.describe_index(collection_name)
        if desc.status.get("ready", False):
            break
        time.sleep(2)
    print("Index is ready")

    index = pc.Index(collection_name)

    batch_size = 100
    inserted = 0
    for ids, vectors, metadatas, contents in dataset.batched(batch_size):
        upsert_data = []
        for i in range(len(ids)):
            meta = {**metadatas[i], "content": contents[i]}
            upsert_data.append((ids[i], vectors[i].tolist(), meta))
        index.upsert(vectors=upsert_data)
        inserted += len(ids)
        print(f"  Inserted {inserted}/{dataset.num_vectors}", end="\r")

    # Give Pinecone a moment to reflect the count
    time.sleep(5)
    stats = index.describe_index_stats()
    print(f"\nDone. Index '{collection_name}' has {stats.total_vector_count} vectors.")
