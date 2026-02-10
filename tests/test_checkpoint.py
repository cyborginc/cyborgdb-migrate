import json
from pathlib import Path

import pytest

from cyborgdb_migrate.checkpoint import (
    CheckpointData,
    checkpoint_path,
    delete_checkpoint,
    load_checkpoint,
    save_checkpoint,
)


@pytest.fixture(autouse=True)
def use_tmp_dir(tmp_path, monkeypatch):
    """Redirect checkpoint dir to a temp directory."""
    import cyborgdb_migrate.checkpoint as cp

    monkeypatch.setattr(cp, "CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    return tmp_path / "checkpoints"


class TestCheckpointPath:
    def test_basic(self):
        p = checkpoint_path("pinecone", "my-index", "dest-index")
        assert p.name == "pinecone_my-index_dest-index.json"

    def test_sanitizes_slashes(self):
        p = checkpoint_path("pinecone", "ns/index", "dest/idx")
        assert "/" not in p.name or str(p).count("/") == str(p.parent).count("/") + 1


class TestSaveLoadCheckpoint:
    def test_save_and_load(self):
        data = CheckpointData(
            source_type="qdrant",
            source_index="collection1",
            dest_index="dest1",
            vectors_migrated=500,
            vectors_total=1000,
            cursor="abc123",
            batch_size=100,
            batches_completed=5,
        )
        save_checkpoint(data)

        loaded = load_checkpoint("qdrant", "collection1", "dest1")
        assert loaded is not None
        assert loaded.source_type == "qdrant"
        assert loaded.vectors_migrated == 500
        assert loaded.cursor == "abc123"
        assert loaded.updated_at != ""

    def test_load_nonexistent(self):
        result = load_checkpoint("nope", "nope", "nope")
        assert result is None

    def test_save_sets_timestamps(self):
        data = CheckpointData(source_type="x", source_index="y", dest_index="z")
        save_checkpoint(data)
        loaded = load_checkpoint("x", "y", "z")
        assert loaded is not None
        assert loaded.started_at != ""
        assert loaded.updated_at != ""

    def test_save_preserves_started_at(self):
        data = CheckpointData(
            source_type="x",
            source_index="y",
            dest_index="z",
            started_at="2025-01-01T00:00:00+00:00",
        )
        save_checkpoint(data)
        loaded = load_checkpoint("x", "y", "z")
        assert loaded is not None
        assert loaded.started_at == "2025-01-01T00:00:00+00:00"

    def test_overwrite_checkpoint(self):
        data = CheckpointData(
            source_type="a", source_index="b", dest_index="c", vectors_migrated=100
        )
        save_checkpoint(data)
        data.vectors_migrated = 200
        save_checkpoint(data)
        loaded = load_checkpoint("a", "b", "c")
        assert loaded is not None
        assert loaded.vectors_migrated == 200


class TestDeleteCheckpoint:
    def test_delete_existing(self):
        data = CheckpointData(source_type="a", source_index="b", dest_index="c")
        save_checkpoint(data)
        assert load_checkpoint("a", "b", "c") is not None
        delete_checkpoint("a", "b", "c")
        assert load_checkpoint("a", "b", "c") is None

    def test_delete_nonexistent(self):
        # Should not raise
        delete_checkpoint("x", "y", "z")
