import os
from pathlib import Path

import pytest

from cyborgdb_migrate.config import expand_env_vars, load_config


class TestExpandEnvVars:
    def test_basic_expansion(self, monkeypatch):
        monkeypatch.setenv("MY_VAR", "hello")
        assert expand_env_vars("${MY_VAR}") == "hello"

    def test_multiple_vars(self, monkeypatch):
        monkeypatch.setenv("A", "foo")
        monkeypatch.setenv("B", "bar")
        assert expand_env_vars("${A}/${B}") == "foo/bar"

    def test_no_vars(self):
        assert expand_env_vars("plain text") == "plain text"

    def test_missing_var_raises(self):
        # Ensure the var is not set
        os.environ.pop("NONEXISTENT_VAR_XYZ", None)
        with pytest.raises(ValueError, match="NONEXISTENT_VAR_XYZ"):
            expand_env_vars("${NONEXISTENT_VAR_XYZ}")

    def test_partial_string(self, monkeypatch):
        monkeypatch.setenv("HOST", "localhost")
        assert expand_env_vars("http://${HOST}:8000") == "http://localhost:8000"

    def test_empty_value(self, monkeypatch):
        monkeypatch.setenv("EMPTY", "")
        assert expand_env_vars("prefix${EMPTY}suffix") == "prefixsuffix"


class TestLoadConfig:
    def _write_toml(self, tmp_path: Path, content: str) -> str:
        p = tmp_path / "config.toml"
        p.write_text(content)
        return str(p)

    def test_full_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PINECONE_KEY", "pk-123")
        monkeypatch.setenv("CYBORG_HOST", "https://cyborg.example.com")
        monkeypatch.setenv("CYBORG_KEY", "ck-456")
        path = self._write_toml(
            tmp_path,
            """
[source]
type = "pinecone"
api_key = "${PINECONE_KEY}"
index = "my-index"
namespace = "default"

[destination]
host = "${CYBORG_HOST}"
api_key = "${CYBORG_KEY}"
create_index = true
index_name = "my-index"
index_type = "ivfflat"
key_file = "./my-key.key"

[options]
batch_size = 200
checkpoint_every = 5
verify = true
spot_check_per_batch = 8
""",
        )
        config = load_config(path)
        assert config.source_type == "pinecone"
        assert config.source_credentials == {"api_key": "pk-123"}
        assert config.source_index == "my-index"
        assert config.source_namespace == "default"
        assert config.destination_host == "https://cyborg.example.com"
        assert config.destination_api_key == "ck-456"
        assert config.create_index is True
        assert config.index_name == "my-index"
        assert config.index_type == "ivfflat"
        assert config.key_file == "./my-key.key"
        assert config.batch_size == 200
        assert config.checkpoint_every == 5
        assert config.spot_check_per_batch == 8

    def test_missing_source_type(self, tmp_path):
        path = self._write_toml(
            tmp_path,
            """
[source]
index = "idx"

[destination]
host = "h"
api_key = "k"
index_name = "n"
""",
        )
        with pytest.raises(ValueError, match="source.*type"):
            load_config(path)

    def test_missing_source_index(self, tmp_path):
        path = self._write_toml(
            tmp_path,
            """
[source]
type = "pinecone"

[destination]
host = "h"
api_key = "k"
index_name = "n"
""",
        )
        with pytest.raises(ValueError, match="source.*index"):
            load_config(path)

    def test_missing_destination_host(self, tmp_path):
        path = self._write_toml(
            tmp_path,
            """
[source]
type = "pinecone"
index = "idx"

[destination]
api_key = "k"
index_name = "n"
""",
        )
        with pytest.raises(ValueError, match="destination.*host"):
            load_config(path)

    def test_missing_env_var_in_config(self, tmp_path):
        os.environ.pop("UNDEFINED_THING_ABC", None)
        path = self._write_toml(
            tmp_path,
            """
[source]
type = "pinecone"
api_key = "${UNDEFINED_THING_ABC}"
index = "idx"

[destination]
host = "h"
api_key = "k"
index_name = "n"
""",
        )
        with pytest.raises(ValueError, match="UNDEFINED_THING_ABC"):
            load_config(path)

    def test_defaults(self, tmp_path):
        path = self._write_toml(
            tmp_path,
            """
[source]
type = "qdrant"
index = "col1"

[destination]
host = "http://localhost:8000"
api_key = "key"
index_name = "dest"
""",
        )
        config = load_config(path)
        assert config.batch_size == 100
        assert config.checkpoint_every == 10
        assert config.verify is True
        assert config.spot_check_per_batch == 4
        assert config.source_namespace is None
        assert config.create_index is True

    def test_existing_index_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("IDX_KEY", "base64encodedkey==")
        path = self._write_toml(
            tmp_path,
            """
[source]
type = "chromadb"
index = "my-col"
mode = "local"
path = "/data/chroma"

[destination]
host = "http://localhost:8000"
api_key = "key"
create_index = false
index_name = "existing"
index_key = "${IDX_KEY}"
""",
        )
        config = load_config(path)
        assert config.create_index is False
        assert config.index_key == "base64encodedkey=="
        assert config.source_credentials == {"mode": "local", "path": "/data/chroma"}
