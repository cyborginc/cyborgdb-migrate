"""HDF5 dataset loader and batch generator for SIFT-128 vectors."""

import os
import numpy as np
import h5py

DEFAULT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "cyborgdb-core", "datasets", "sift-128-euclidean.hdf5"
)


class Dataset:
    def __init__(self, path: str = DEFAULT_PATH, num_vectors: int = 10_000):
        path = os.path.abspath(path)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Dataset not found: {path}")

        with h5py.File(path, "r") as f:
            self.vectors = np.array(f["train"][:num_vectors], dtype=np.float32)

        self.num_vectors = len(self.vectors)
        self.dimension = self.vectors.shape[1]
        print(f"Loaded {self.num_vectors} vectors ({self.dimension}d) from {path}")

    def id_for(self, i: int) -> str:
        return f"vec_{i:07d}"

    def metadata_for(self, i: int) -> dict:
        return {"category": f"cat_{i % 10}", "seq": i}

    def content_for(self, i: int) -> str:
        return f"SIFT vector {i}"

    def batched(self, batch_size: int):
        """Yield (ids, vectors_np, metadatas, contents) tuples."""
        for start in range(0, self.num_vectors, batch_size):
            end = min(start + batch_size, self.num_vectors)
            ids = [self.id_for(i) for i in range(start, end)]
            vectors = self.vectors[start:end]
            metadatas = [self.metadata_for(i) for i in range(start, end)]
            contents = [self.content_for(i) for i in range(start, end)]
            yield ids, vectors, metadatas, contents
