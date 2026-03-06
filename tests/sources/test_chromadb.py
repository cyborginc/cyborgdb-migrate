import sys
from unittest.mock import MagicMock, patch

import pytest

from cyborgdb_migrate.sources.chromadb import ChromaDBSource


class TestChromaDBCredentials:
    def test_credential_fields(self):
        source = ChromaDBSource()
        fields = source.credential_fields()
        assert len(fields) == 3

        keys = [f.key for f in fields]
        assert "mode" in keys
        assert "host" in keys
        assert "path" in keys

        mode_field = fields[0]
        assert mode_field.options == ["Remote", "Local"]

        host_field = fields[1]
        assert host_field.visible_when == {"mode": "Remote"}

        path_field = fields[2]
        assert path_field.visible_when == {"mode": "Local"}

    def test_name(self):
        assert ChromaDBSource().name() == "ChromaDB"


class TestChromaDBConfigure:
    def test_configure_remote_with_port(self):
        source = ChromaDBSource()
        source.configure({"mode": "Remote", "host": "chroma-host:9000"})
        assert source._mode == "remote"
        assert source._host == "chroma-host"
        assert source._port == 9000

    def test_configure_remote_without_port(self):
        source = ChromaDBSource()
        source.configure({"mode": "Remote", "host": "chroma-host"})
        assert source._mode == "remote"
        assert source._host == "chroma-host"
        assert source._port == 8100

    def test_configure_remote_default(self):
        source = ChromaDBSource()
        source.configure({"mode": "Remote", "host": "localhost:8100"})
        assert source._mode == "remote"
        assert source._host == "localhost"
        assert source._port == 8100

    def test_configure_remote_empty_host_raises(self):
        source = ChromaDBSource()
        with pytest.raises(ValueError, match="host is required"):
            source.configure({"mode": "Remote", "host": ""})

    def test_configure_remote_invalid_port(self):
        source = ChromaDBSource()
        with pytest.raises(ValueError, match="port"):
            source.configure({"mode": "Remote", "host": "localhost:abc"})

    def test_configure_local(self):
        source = ChromaDBSource()
        source.configure({"mode": "Local", "path": "/data/chroma"})
        assert source._mode == "local"
        assert source._path == "/data/chroma"

    def test_configure_local_empty_path_raises(self):
        source = ChromaDBSource()
        with pytest.raises(ValueError, match="path is required"):
            source.configure({"mode": "Local", "path": ""})


class TestChromaDBConnect:
    def test_connect_remote(self):
        mock_chromadb_mod = MagicMock()
        source = ChromaDBSource()
        source._mode = "remote"
        source._host = "localhost"
        source._port = 8100

        with patch.dict(sys.modules, {"chromadb": mock_chromadb_mod}):
            source.connect()

        mock_chromadb_mod.HttpClient.assert_called_once_with(host="localhost", port=8100)
        mock_chromadb_mod.HttpClient.return_value.heartbeat.assert_called_once()

    def test_connect_local(self):
        mock_chromadb_mod = MagicMock()
        source = ChromaDBSource()
        source._mode = "local"
        source._path = "/data"

        with patch.dict(sys.modules, {"chromadb": mock_chromadb_mod}):
            source.connect()

        mock_chromadb_mod.PersistentClient.assert_called_once_with(path="/data")
        mock_chromadb_mod.PersistentClient.return_value.heartbeat.assert_called_once()


class TestChromaDBInspect:
    def test_inspect(self):
        source = ChromaDBSource()
        source._client = MagicMock()

        collection = MagicMock()
        source._client.get_collection.return_value = collection
        collection.count.return_value = 500
        collection.get.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}

        info = source.inspect("my-col")
        assert info.source_type == "chromadb"
        assert info.dimension == 3
        assert info.vector_count == 500
        assert info.metric == "cosine"


class TestChromaDBExtract:
    def test_extract_with_documents(self):
        source = ChromaDBSource()
        source._client = MagicMock()

        collection = MagicMock()
        source._client.get_collection.return_value = collection

        collection.get.side_effect = [
            {
                "ids": ["d1", "d2"],
                "embeddings": [[0.1, 0.2], [0.3, 0.4]],
                "metadatas": [{"k": "v"}, {}],
                "documents": ["Hello world", None],
            },
            {"ids": [], "embeddings": [], "metadatas": [], "documents": []},
        ]

        batches = list(source.extract("col", batch_size=10))
        assert len(batches) == 1
        batch, cursor = batches[0]
        assert len(batch) == 2
        assert batch[0].id == "d1"
        assert batch[0].vector == [0.1, 0.2]
        assert batch[0].metadata == {"k": "v"}
        assert batch[0].contents == "Hello world"
        assert batch[1].contents is None
        assert cursor == "2"

    def test_extract_pagination(self):
        source = ChromaDBSource()
        source._client = MagicMock()

        collection = MagicMock()
        source._client.get_collection.return_value = collection

        collection.get.side_effect = [
            {
                "ids": ["d1", "d2"],
                "embeddings": [[0.1], [0.2]],
                "metadatas": [{}, {}],
                "documents": [None, None],
            },
            {
                "ids": ["d3"],
                "embeddings": [[0.3]],
                "metadatas": [{}],
                "documents": [None],
            },
            {"ids": [], "embeddings": [], "metadatas": [], "documents": []},
        ]

        batches = list(source.extract("col", batch_size=2))
        assert len(batches) == 2
        assert batches[0][1] == "2"
        assert batches[1][1] == "3"

    def test_extract_resume(self):
        source = ChromaDBSource()
        source._client = MagicMock()

        collection = MagicMock()
        source._client.get_collection.return_value = collection

        collection.get.side_effect = [
            {"ids": ["d3"], "embeddings": [[0.3]], "metadatas": [{}], "documents": [None]},
            {"ids": [], "embeddings": [], "metadatas": [], "documents": []},
        ]

        batches = list(source.extract("col", batch_size=10, resume_from="2"))
        call_kwargs = collection.get.call_args_list[0][1]
        assert call_kwargs["offset"] == 2
