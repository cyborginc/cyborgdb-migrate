import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cyborgdb_migrate.cli import _decode_key
from cyborgdb_migrate.models import MigrationResult, SourceInfo


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


class TestDecodeKey:
    def test_hex_key(self):
        key_hex = "00" * 32
        result = _decode_key(key_hex)
        assert result == b"\x00" * 32

    def test_base64_fallback(self):
        raw = b"\x01\x02\x03\x04"
        b64 = base64.b64encode(raw).decode()
        result = _decode_key(b64)
        assert result == raw

    def test_invalid_key_raises(self):
        with pytest.raises(Exception):
            _decode_key("not-hex-and-not-base64!!!")


class TestRunHeadless:
    @patch("cyborgdb.Client")
    @patch("cyborgdb_migrate.engine.MigrationEngine")
    @patch("cyborgdb_migrate.destination.CyborgDestination")
    @patch("cyborgdb_migrate.sources.SOURCE_REGISTRY")
    def test_happy_path(
        self, mock_registry, mock_dest_cls, mock_engine_cls, mock_client_cls, tmp_path,
        monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)
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
        self, mock_registry, mock_dest_cls, mock_engine_cls, mock_client_cls, tmp_path,
        monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)
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

    @patch("cyborgdb_migrate.destination.CyborgDestination")
    @patch("cyborgdb_migrate.sources.SOURCE_REGISTRY")
    def test_version_mismatch_exits_with_clear_error(
        self, mock_registry, mock_dest_cls, tmp_path, capsys
    ):
        from cyborgdb_migrate.version_check import VersionMismatch

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
        mock_dest.connect.side_effect = VersionMismatch(
            server_version="0.17.0", migrate_version="0.16.2"
        )
        mock_dest_cls.return_value = mock_dest

        from cyborgdb_migrate.cli import run_headless

        with pytest.raises(SystemExit) as exc_info:
            run_headless(
                config_path, batch_size=50, resume=False,
                log_file="/dev/null", quiet=True,
            )
        assert exc_info.value.code == 1

        # Source-side state must not have been opened with a destructive operation
        # before the version check failed.
        mock_source.connect.assert_called_once()  # connect happens first; that's ok
        # No engine, no upsert, etc. — destination.connect raised before that path.

    @patch("cyborgdb_migrate.destination.CyborgDestination")
    @patch("cyborgdb_migrate.sources.SOURCE_REGISTRY")
    def test_health_unreachable_exits_with_clear_error(
        self, mock_registry, mock_dest_cls, tmp_path
    ):
        from cyborgdb_migrate.version_check import HealthUnreachable

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
        mock_dest.connect.side_effect = HealthUnreachable(
            host="http://localhost:9999", cause="network error"
        )
        mock_dest_cls.return_value = mock_dest

        from cyborgdb_migrate.cli import run_headless

        with pytest.raises(SystemExit) as exc_info:
            run_headless(
                config_path, batch_size=50, resume=False,
                log_file="/dev/null", quiet=True,
            )
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
            run_headless(
                config_path, batch_size=100, resume=False,
                log_file="/dev/null", quiet=True,
            )
        assert exc_info.value.code == 1


CREATE_CONFIG_TEMPLATE = """\
[source]
type = "pinecone"
api_key = "pk-test"
index = "my-index"

[destination]
host = "http://localhost:8000"
api_key = "ck-test"
create_index = true
index_name = "dest-index"
{extra}
"""


def _setup_success_mocks(mock_registry, mock_dest_cls, mock_engine_cls):
    """Wire up source/destination/engine mocks for a run that completes cleanly."""
    mock_source = MagicMock()
    mock_source.name.return_value = "Pinecone"
    mock_source.inspect.return_value = SourceInfo(
        source_type="pinecone",
        index_or_collection_name="my-index",
        dimension=128,
        vector_count=100,
        metric="cosine",
    )
    mock_registry.items.return_value = [("Pinecone", MagicMock(return_value=mock_source))]

    mock_dest = MagicMock()
    mock_dest_cls.return_value = mock_dest

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
    return mock_dest


@patch("cyborgdb.Client")
@patch("cyborgdb_migrate.engine.MigrationEngine")
@patch("cyborgdb_migrate.destination.CyborgDestination")
@patch("cyborgdb_migrate.sources.SOURCE_REGISTRY")
class TestCreateIndexKeyHandling:
    def test_supplied_index_key_is_used(
        self, mock_registry, mock_dest_cls, mock_engine_cls, mock_client_cls, tmp_path
    ):
        key_hex = "ab" * 32
        config_path = _write_config(
            tmp_path, CREATE_CONFIG_TEMPLATE.format(extra=f'index_key = "{key_hex}"')
        )
        mock_dest = _setup_success_mocks(mock_registry, mock_dest_cls, mock_engine_cls)

        from cyborgdb_migrate.cli import run_headless

        run_headless(config_path, batch_size=50, resume=False, log_file="/dev/null", quiet=True)

        mock_client_cls.generate_key.assert_not_called()
        assert mock_dest.create_index.call_args.kwargs["index_key"] == bytes.fromhex(key_hex)

    def test_existing_key_file_is_used(
        self, mock_registry, mock_dest_cls, mock_engine_cls, mock_client_cls, tmp_path
    ):
        key_hex = "cd" * 32
        key_file = tmp_path / "my.key"
        key_file.write_text(key_hex + "\n")
        config_path = _write_config(
            tmp_path, CREATE_CONFIG_TEMPLATE.format(extra=f'key_file = "{key_file}"')
        )
        mock_dest = _setup_success_mocks(mock_registry, mock_dest_cls, mock_engine_cls)

        from cyborgdb_migrate.cli import run_headless

        run_headless(config_path, batch_size=50, resume=False, log_file="/dev/null", quiet=True)

        mock_client_cls.generate_key.assert_not_called()
        assert mock_dest.create_index.call_args.kwargs["index_key"] == bytes.fromhex(key_hex)
        assert key_file.read_text().strip() == key_hex  # untouched

    def test_generated_key_saved_to_default_path_under_quiet(
        self, mock_registry, mock_dest_cls, mock_engine_cls, mock_client_cls, tmp_path,
        monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)
        config_path = _write_config(tmp_path, CREATE_CONFIG_TEMPLATE.format(extra=""))
        mock_dest = _setup_success_mocks(mock_registry, mock_dest_cls, mock_engine_cls)
        mock_client_cls.generate_key.return_value = b"\x01" * 32

        from cyborgdb_migrate.cli import run_headless

        run_headless(config_path, batch_size=50, resume=False, log_file="/dev/null", quiet=True)

        key_path = tmp_path / "cyborgdb-migrate-checkpoints" / "dest-index.key"
        assert key_path.exists()
        assert key_path.read_text().strip() == "01" * 32
        assert (key_path.stat().st_mode & 0o777) == 0o600
        assert mock_dest.create_index.call_args.kwargs["index_key"] == b"\x01" * 32

    def test_generated_key_saved_to_configured_key_file(
        self, mock_registry, mock_dest_cls, mock_engine_cls, mock_client_cls, tmp_path,
        monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)
        key_file = tmp_path / "keys" / "new.key"
        config_path = _write_config(
            tmp_path, CREATE_CONFIG_TEMPLATE.format(extra=f'key_file = "{key_file}"')
        )
        _setup_success_mocks(mock_registry, mock_dest_cls, mock_engine_cls)
        mock_client_cls.generate_key.return_value = b"\x02" * 32

        from cyborgdb_migrate.cli import run_headless

        run_headless(config_path, batch_size=50, resume=False, log_file="/dev/null", quiet=True)

        assert key_file.read_text().strip() == "02" * 32
        assert (key_file.stat().st_mode & 0o777) == 0o600
        assert not (tmp_path / "cyborgdb-migrate-checkpoints" / "dest-index.key").exists()

    def test_refuses_to_overwrite_existing_default_key_file(
        self, mock_registry, mock_dest_cls, mock_engine_cls, mock_client_cls, tmp_path,
        monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)
        key_path = tmp_path / "cyborgdb-migrate-checkpoints" / "dest-index.key"
        key_path.parent.mkdir(parents=True)
        key_path.write_text("ee" * 32 + "\n")
        config_path = _write_config(tmp_path, CREATE_CONFIG_TEMPLATE.format(extra=""))
        mock_dest = _setup_success_mocks(mock_registry, mock_dest_cls, mock_engine_cls)
        mock_client_cls.generate_key.return_value = b"\x03" * 32

        from cyborgdb_migrate.cli import run_headless

        with pytest.raises(SystemExit) as exc_info:
            run_headless(
                config_path, batch_size=50, resume=False, log_file="/dev/null", quiet=True
            )
        assert exc_info.value.code == 1
        assert key_path.read_text().strip() == "ee" * 32  # untouched
        mock_dest.create_index.assert_not_called()

    def test_kms_name_with_local_key_errors(
        self, mock_registry, mock_dest_cls, mock_engine_cls, mock_client_cls, tmp_path
    ):
        extra = 'kms_name = "aws-kms"\nindex_key = "ff{}"'.format("ff" * 31)
        config_path = _write_config(tmp_path, CREATE_CONFIG_TEMPLATE.format(extra=extra))
        mock_dest = _setup_success_mocks(mock_registry, mock_dest_cls, mock_engine_cls)

        from cyborgdb_migrate.cli import run_headless

        with pytest.raises(SystemExit) as exc_info:
            run_headless(
                config_path, batch_size=50, resume=False, log_file="/dev/null", quiet=True
            )
        assert exc_info.value.code == 1
        mock_dest.create_index.assert_not_called()
