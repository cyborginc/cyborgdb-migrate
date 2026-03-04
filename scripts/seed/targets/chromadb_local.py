"""Seed a local ChromaDB with SIFT-128 vectors."""

import chromadb


def seed(dataset, args):
    path = args.chromadb_path
    collection_name = args.collection_name or "sift_128"

    print(f"Connecting to ChromaDB (local) at {path}")
    client = chromadb.PersistentClient(path=path)

    # Drop if exists
    try:
        client.delete_collection(collection_name)
        print(f"Dropped existing collection '{collection_name}'")
    except Exception:
        pass

    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "l2"},
    )
    print(f"Created collection '{collection_name}'")

    batch_size = 500
    inserted = 0
    for ids, vectors, metadatas, contents in dataset.batched(batch_size):
        collection.add(
            ids=ids,
            embeddings=vectors.tolist(),
            metadatas=metadatas,
            documents=contents,
        )
        inserted += len(ids)
        print(f"  Inserted {inserted}/{dataset.num_vectors}", end="\r")

    print(f"\nDone. Collection '{collection_name}' has {collection.count()} vectors.")
