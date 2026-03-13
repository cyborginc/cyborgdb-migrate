from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

CHECKPOINT_DIR = "./cyborgdb-migrate-checkpoints"


@dataclass
class CheckpointData:
    version: int = 1
    source_type: str = ""
    source_index: str = ""
    dest_index: str = ""
    namespace: str | None = None
    cursor: str | None = None
    vectors_migrated: int = 0
    vectors_total: int = 0
    started_at: str = ""
    updated_at: str = ""
    batch_size: int = 100
    batches_completed: int = 0


def checkpoint_path(source_type: str, source_index: str, dest_index: str) -> Path:
    """Return the checkpoint file path for a given migration."""
    safe_name = f"{source_type}_{source_index}_{dest_index}.json"
    # Sanitize filename
    safe_name = safe_name.replace("/", "_").replace("\\", "_")
    return Path(CHECKPOINT_DIR) / safe_name


def save_checkpoint(data: CheckpointData) -> Path:
    """Atomically save checkpoint data to disk."""
    path = checkpoint_path(data.source_type, data.source_index, data.dest_index)
    path.parent.mkdir(parents=True, exist_ok=True)

    data.updated_at = datetime.now(timezone.utc).isoformat()
    if not data.started_at:
        data.started_at = data.updated_at

    # Atomic write: write to temp file then rename
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(asdict(data), f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return path


def load_checkpoint(source_type: str, source_index: str, dest_index: str) -> CheckpointData | None:
    """Load checkpoint data if it exists. Returns None if no checkpoint found."""
    path = checkpoint_path(source_type, source_index, dest_index)
    if not path.exists():
        return None
    with open(path) as f:
        raw = json.load(f)
    return CheckpointData(**raw)


def delete_checkpoint(source_type: str, source_index: str, dest_index: str) -> None:
    """Delete a checkpoint file if it exists."""
    path = checkpoint_path(source_type, source_index, dest_index)
    if path.exists():
        path.unlink()
