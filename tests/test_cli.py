from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cyborgdb_migrate.models import MigrationResult, SourceInfo, VectorRecord


def _write_config(tmp_path: Path, content: str) -> str:
    p = tmp_path / "config.toml"
    p.write_text(content)
    return str(p)


BASIC_CONFIG = """\
[source]
type = "pinecone"
api_key = "pk-test"
index = "my-index"

[destination]
host = "http://localhost:8000"
api_key = "ck-test"
create_index = true
index_name = "dest-index"
index_type = "ivfflat"

[options]
batch_size = 50
"""

EXISTING_INDEX_CONFIG = """\
[source]
type = "pinecone"
api_key = "pk-test"
index = "my-index"

[destination]
host = "http://localhost:8000"
api_key = "ck-test"
create_index = false
index_name = "existing-index"
index_key = "0000000000000000000000000000000000000000000000000000000000000000"

[options]
batch_size = 50
"""


class TestRunHeadless:
    @patch("cyborgdb.Client")
    @patch("cyborgdb_migrate.engine.MigrationEngine")
    @patch("cyborgdb_migrate.destination.CyborgDestination")
    @patch("cyborgdb_migrate.sources.SOURCE_REGISTRY")
    def test_happy_path(self, mock_registry, mock_dest_cls, mock_engine_cls, mock_client_cls, tmp_path):
        config_path = _write_config(tmp_path, BASIC_CONFIG)

        # Mock source
        mock_source = MagicMock()
        mock_source.name.return_value = "Pinecone"
        mock_source.inspect.return_value = SourceInfo(
            source_type="pinecone",
            index_or_collection_name="my-index",
            dimension=128,
            vector_count=100,
            metric="cosine",
        )
        mock_source_cls = MagicMock(return_value=mock_source)
        mock_registry.items.return_value = [("Pinecone", mock_source_cls)]

        # Mock destination
        mock_dest = MagicMock()
        mock_dest_cls.return_value = mock_dest

        # Mock Client.generate_key
        mock_client_cls.generate_key.return_value = b"\x00" * 32

        # Mock engine
        mock_engine = MagicMock()
        mock_engine.run.return_value = MigrationResult(
            vectors_migrated=100,
            vectors_expected=100,
            duration_seconds=1.0,
            spot_check_passed=True,
            spot_check_details="100/100 verified",
            index_name="dest-index",
        )
        mock_engine_cls.return_value = mock_engine

        from cyborgdb_migrate.cli import run_headless

        run_headless(config_path, batch_size=50, resume=False, log_file="/dev/null", quiet=True)

        mock_source.configure.assert_called_once()
        mock_source.connect.assert_called_once()
        mock_dest.connect.assert_called_once_with("http://localhost:8000", "ck-test")
        mock_engine.run.assert_called_once()

    @patch("cyborgdb.Client")
    @patch("cyborgdb_migrate.engine.MigrationEngine")
    @patch("cyborgdb_migrate.destination.CyborgDestination")
    @patch("cyborgdb_migrate.sources.SOURCE_REGISTRY")
    def test_spot_check_failure_exits_with_code_2(
        self, mock_registry, mock_dest_cls, mock_engine_cls, mock_client_cls, tmp_path
    ):
        config_path = _write_config(tmp_path, BASIC_CONFIG)

        mock_source = MagicMock()
        mock_source.name.return_value = "Pinecone"
        mock_source.inspect.return_value = SourceInfo(
            source_type="pinecone",
            index_or_collection_name="my-index",
            dimension=128,
            vector_count=100,
        )
        mock_source_cls = MagicMock(return_value=mock_source)
        mock_registry.items.return_value = [("Pinecone", mock_source_cls)]

        mock_dest = MagicMock()
        mock_dest_cls.return_value = mock_dest
        mock_client_cls.generate_key.return_value = b"\x00" * 32

        mock_engine = MagicMock()
        mock_engine.run.return_value = MigrationResult(
            vectors_migrated=100,
            vectors_expected=100,
            duration_seconds=1.0,
            spot_check_passed=False,
            spot_check_details="5/100 mismatched",
            index_name="dest-index",
        )
        mock_engine_cls.return_value = mock_engine

        from cyborgdb_migrate.cli import run_headless

        with pytest.raises(SystemExit) as exc_info:
            run_headless(config_path, batch_size=50, resume=False, log_file="/dev/null", quiet=True)
        assert exc_info.value.code == 2

    @patch("cyborgdb_migrate.destination.CyborgDestination")
    @patch("cyborgdb_migrate.sources.SOURCE_REGISTRY")
    def test_dimension_mismatch_existing_index(self, mock_registry, mock_dest_cls, tmp_path):
        config_path = _write_config(tmp_path, EXISTING_INDEX_CONFIG)

        mock_source = MagicMock()
        mock_source.name.return_value = "Pinecone"
        mock_source.inspect.return_value = SourceInfo(
            source_type="pinecone",
            index_or_collection_name="my-index",
            dimension=1536,
            vector_count=100,
        )
        mock_source_cls = MagicMock(return_value=mock_source)
        mock_registry.items.return_value = [("Pinecone", mock_source_cls)]

        mock_dest = MagicMock()
        mock_dest.get_index_dimension.return_value = 768  # Mismatch!
        mock_dest_cls.return_value = mock_dest

        from cyborgdb_migrate.cli import run_headless

        with pytest.raises(SystemExit) as exc_info:
            run_headless(config_path, batch_size=50, resume=False, log_file="/dev/null", quiet=True)
        assert exc_info.value.code == 1

    @patch("cyborgdb_migrate.sources.SOURCE_REGISTRY")
    def test_unknown_source_type_exits(self, mock_registry, tmp_path):
        config_text = """\
[source]
type = "nosuchdb"
index = "idx"

[destination]
host = "http://localhost:8000"
api_key = "k"
create_index = true
index_name = "dest"
"""
        config_path = _write_config(tmp_path, config_text)
        mock_registry.items.return_value = [("Pinecone", MagicMock())]

        from cyborgdb_migrate.cli import run_headless

        with pytest.raises(SystemExit) as exc_info:
            run_headless(config_path, batch_size=100, resume=False, log_file="/dev/null", quiet=True)
        assert exc_info.value.code == 1
