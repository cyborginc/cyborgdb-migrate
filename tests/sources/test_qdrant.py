import sys
from unittest.mock import MagicMock, patch

import pytest

from cyborgdb_migrate.sources.qdrant import QdrantSource


class TestQdrantCredentials:
    def test_credential_fields(self):
        source = QdrantSource()
        fields = source.credential_fields()
        assert len(fields) == 2
        assert fields[0].key == "host"
        assert fields[0].default == "http://localhost:6333"
        assert fields[1].key == "api_key"
        assert fields[1].required is False

    def test_configure_defaults(self):
        source = QdrantSource()
        source.configure({"host": "http://qdrant:6333"})
        assert source._host == "http://qdrant:6333"
        assert source._api_key is None

    def test_configure_with_api_key(self):
        source = QdrantSource()
        source.configure({"host": "http://qdrant:6333", "api_key": "my-key"})
        assert source._api_key == "my-key"

    def test_configure_empty_host(self):
        source = QdrantSource()
        with pytest.raises(ValueError, match="host"):
            source.configure({"host": ""})

    def test_name(self):
        assert QdrantSource().name() == "Qdrant"


class TestQdrantConnect:
    def test_connect(self):
        mock_cls = MagicMock()
        mock_mod = MagicMock()
        mock_mod.QdrantClient = mock_cls

        source = QdrantSource()
        source._host = "http://localhost:6333"
        source._api_key = None

        with patch.dict(sys.modules, {"qdrant_client": mock_mod}):
            source.connect()

        mock_cls.assert_called_once_with(url="http://localhost:6333")

    def test_connect_with_api_key(self):
        mock_cls = MagicMock()
        mock_mod = MagicMock()
        mock_mod.QdrantClient = mock_cls

        source = QdrantSource()
        source._host = "http://cloud.qdrant.io"
        source._api_key = "cloud-key"

        with patch.dict(sys.modules, {"qdrant_client": mock_mod}):
            source.connect()

        mock_cls.assert_called_once_with(url="http://cloud.qdrant.io", api_key="cloud-key")


class TestQdrantInspect:
    def test_inspect(self):
        source = QdrantSource()
        source._client = MagicMock()

        info = MagicMock()
        info.config.params.vectors.size = 768
        info.config.params.vectors.distance = "Cosine"
        info.points_count = 5000
        source._client.get_collection.return_value = info

        result = source.inspect("my-collection")
        assert result.source_type == "qdrant"
        assert result.dimension == 768
        assert result.vector_count == 5000
        assert result.metric == "cosine"
        assert result.namespaces is None


class TestQdrantExtract:
    def test_extract_pagination(self):
        source = QdrantSource()
        source._client = MagicMock()

        rec1 = MagicMock()
        rec1.id = "id-1"
        rec1.vector = [0.1, 0.2]
        rec1.payload = {"key": "val"}

        rec2 = MagicMock()
        rec2.id = "id-2"
        rec2.vector = [0.3, 0.4]
        rec2.payload = {}

        # First page
        source._client.scroll.side_effect = [
            ([rec1, rec2], "next-offset"),
            ([], None),
        ]

        batches = list(source.extract("col", batch_size=10))
        assert len(batches) == 1
        batch, cursor = batches[0]
        assert len(batch) == 2
        assert batch[0].id == "id-1"
        assert batch[0].vector == [0.1, 0.2]
        assert batch[0].metadata == {"key": "val"}
        assert cursor == "next-offset"

    def test_extract_yields_tuples(self):
        source = QdrantSource()
        source._client = MagicMock()

        rec = MagicMock()
        rec.id = "id-1"
        rec.vector = [0.1]
        rec.payload = None

        source._client.scroll.side_effect = [
            ([rec], None),
        ]

        for batch, cursor in source.extract("col", batch_size=10):
            assert isinstance(batch, list)
            assert batch[0].contents is None
