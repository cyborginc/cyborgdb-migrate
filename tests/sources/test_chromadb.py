import sys
from unittest.mock import MagicMock, patch

import pytest

from cyborgdb_migrate.sources.chromadb import ChromaDBLocalSource, ChromaDBRemoteSource


class TestChromaDBLocalCredentials:
    def test_credential_fields(self):
        source = ChromaDBLocalSource()
        fields = source.credential_fields()
        assert len(fields) == 1

        keys = [f.key for f in fields]
        assert "path" in keys

        # No visible_when on any field
        for f in fields:
            assert f.visible_when is None

    def test_configure(self):
        source = ChromaDBLocalSource()
        source.configure({"path": "/data/chroma"})
        assert source._path == "/data/chroma"

    def test_configure_empty_path(self):
        source = ChromaDBLocalSource()
        with pytest.raises(ValueError, match="path is required"):
            source.configure({"path": ""})

    def test_configure_default_path(self):
        source = ChromaDBLocalSource()
        source.configure({})
        assert source._path == "./chroma_data"

    def test_name(self):
        assert ChromaDBLocalSource().name() == "ChromaDB (Local)"


class TestChromaDBRemoteCredentials:
    def test_credential_fields(self):
        source = ChromaDBRemoteSource()
        fields = source.credential_fields()
        assert len(fields) == 2

        keys = [f.key for f in fields]
        assert "host" in keys
        assert "port" in keys

        # No visible_when on any field
        for f in fields:
            assert f.visible_when is None

    def test_configure(self):
        source = ChromaDBRemoteSource()
        source.configure({"host": "chroma-host", "port": "9000"})
        assert source._host == "chroma-host"
        assert source._port == 9000

    def test_configure_invalid_port(self):
        source = ChromaDBRemoteSource()
        with pytest.raises(ValueError, match="port"):
            source.configure({"port": "abc"})

    def test_name(self):
        assert ChromaDBRemoteSource().name() == "ChromaDB (Remote)"


class TestChromaDBConnect:
    def test_connect_local(self):
        mock_chromadb_mod = MagicMock()
        source = ChromaDBLocalSource()
        source._path = "/data"

        with patch.dict(sys.modules, {"chromadb": mock_chromadb_mod}):
            source.connect()

        mock_chromadb_mod.PersistentClient.assert_called_once_with(path="/data")
        mock_chromadb_mod.PersistentClient.return_value.heartbeat.assert_called_once()

    def test_connect_remote(self):
        mock_chromadb_mod = MagicMock()
        source = ChromaDBRemoteSource()
        source._host = "localhost"
        source._port = 8000

        with patch.dict(sys.modules, {"chromadb": mock_chromadb_mod}):
            source.connect()

        mock_chromadb_mod.HttpClient.assert_called_once_with(host="localhost", port=8000)


class TestChromaDBInspect:
    def test_inspect(self):
        source = ChromaDBLocalSource()
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
        source = ChromaDBLocalSource()
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
        source = ChromaDBRemoteSource()
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
        assert batches[0][1] == "2"  # cursor = offset after first batch
        assert batches[1][1] == "3"

    def test_extract_resume(self):
        source = ChromaDBLocalSource()
        source._client = MagicMock()

        collection = MagicMock()
        source._client.get_collection.return_value = collection

        collection.get.side_effect = [
            {"ids": ["d3"], "embeddings": [[0.3]], "metadatas": [{}], "documents": [None]},
            {"ids": [], "embeddings": [], "metadatas": [], "documents": []},
        ]

        batches = list(source.extract("col", batch_size=10, resume_from="2"))
        # Should have called get with offset=2
        call_kwargs = collection.get.call_args_list[0][1]
        assert call_kwargs["offset"] == 2
