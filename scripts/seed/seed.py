#!/usr/bin/env python3
"""Seed vector databases with SIFT-128 test data."""

import argparse
import importlib
import time
import sys

from dataset import Dataset

TARGETS = {
    "milvus": "targets.milvus",
    "pinecone": "targets.pinecone_",
    "weaviate": "targets.weaviate_",
    "chromadb-local": "targets.chromadb_local",
    "chromadb-remote": "targets.chromadb_remote",
    "qdrant": "targets.qdrant",
}


def run_target(name: str, module_path: str, dataset: Dataset, args):
    print(f"\n{'='*60}")
    print(f"Seeding: {name}")
    print(f"{'='*60}")
    start = time.time()
    try:
        mod = importlib.import_module(module_path)
        mod.seed(dataset, args)
        elapsed = time.time() - start
        print(f"[{name}] Completed in {elapsed:.1f}s")
    except Exception as e:
        elapsed = time.time() - start
        print(f"[{name}] FAILED after {elapsed:.1f}s: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Seed vector databases with SIFT-128 data")
    parser.add_argument("target", choices=[*TARGETS.keys(), "all"], help="Target database to seed")
    parser.add_argument("-n", "--num-vectors", type=int, default=10_000, help="Number of vectors to load (default: 10000)")
    parser.add_argument("--dataset-path", default=None, help="Path to SIFT-128 HDF5 file")
    parser.add_argument("--collection-name", default=None, help="Override default collection name")

    # Milvus
    parser.add_argument("--milvus-uri", default="http://localhost:19530", help="Milvus URI")

    # Pinecone
    parser.add_argument("--pinecone-api-key", default=None, help="Pinecone API key")

    # Weaviate
    parser.add_argument("--weaviate-host", default="localhost", help="Weaviate host")
    parser.add_argument("--weaviate-port", type=int, default=8080, help="Weaviate HTTP port")
    parser.add_argument("--weaviate-grpc-port", type=int, default=50051, help="Weaviate gRPC port")

    # ChromaDB local
    parser.add_argument("--chromadb-path", default="./chroma_data", help="ChromaDB persistent storage path")

    # ChromaDB remote
    parser.add_argument("--chromadb-host", default="localhost", help="ChromaDB server host")
    parser.add_argument("--chromadb-port", type=int, default=8000, help="ChromaDB server port")

    # Qdrant
    parser.add_argument("--qdrant-host", default="http://localhost:6333", help="Qdrant URL")

    args = parser.parse_args()

    # Load dataset once
    kwargs = {"num_vectors": args.num_vectors}
    if args.dataset_path:
        kwargs["path"] = args.dataset_path
    dataset = Dataset(**kwargs)

    if args.target == "all":
        for name, module_path in TARGETS.items():
            run_target(name, module_path, dataset, args)
    else:
        run_target(args.target, TARGETS[args.target], dataset, args)


if __name__ == "__main__":
    main()
