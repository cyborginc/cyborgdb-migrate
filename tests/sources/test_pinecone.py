import sys
from unittest.mock import MagicMock, patch

import pytest

from cyborgdb_migrate.sources.pinecone import PineconeSource


class TestPineconeCredentials:
    def test_credential_fields(self):
        source = PineconeSource()
        fields = source.credential_fields()
        assert len(fields) == 1
        assert fields[0].key == "api_key"
        assert fields[0].is_secret is True

    def test_configure_valid(self):
        source = PineconeSource()
        source.configure({"api_key": "pk-123"})
        assert source._api_key == "pk-123"

    def test_configure_missing_key(self):
        source = PineconeSource()
        with pytest.raises(ValueError, match="API Key"):
            source.configure({})

    def test_configure_empty_key(self):
        source = PineconeSource()
        with pytest.raises(ValueError, match="API Key"):
            source.configure({"api_key": "  "})

    def test_name(self):
        assert PineconeSource().name() == "Pinecone"


class TestPineconeConnect:
    def test_connect_success(self):
        mock_pc_cls = MagicMock()
        mock_pinecone_mod = MagicMock()
        mock_pinecone_mod.Pinecone = mock_pc_cls

        source = PineconeSource()
        source._api_key = "test-key"

        with patch.dict(sys.modules, {"pinecone": mock_pinecone_mod}):
            source.connect()

        mock_pc_cls.assert_called_once_with(api_key="test-key")
        mock_pc_cls.return_value.list_indexes.assert_called_once()


class TestPineconeInspect:
    def test_inspect(self):
        source = PineconeSource()
        source._client = MagicMock()

        mock_index = MagicMock()
        source._client.Index.return_value = mock_index

        stats = MagicMock()
        stats.dimension = 1536
        stats.total_vector_count = 10000
        stats.namespaces = {
            "": MagicMock(vector_count=7000),
            "products": MagicMock(vector_count=3000),
        }
        mock_index.describe_index_stats.return_value = stats

        info = source.inspect("my-index")
        assert info.source_type == "pinecone"
        assert info.dimension == 1536
        assert info.vector_count == 10000
        assert info.namespaces == ["", "products"]
        assert info.extra["namespace_counts"][""] == 7000


class TestPineconeExtract:
    def test_extract_single_page(self):
        source = PineconeSource()
        source._client = MagicMock()
        mock_index = MagicMock()
        source._client.Index.return_value = mock_index

        # Mock list response
        page = MagicMock()
        page.vectors = ["v1", "v2"]
        page.pagination = MagicMock()
        page.pagination.next = None
        mock_index.list.return_value = page

        # Mock fetch response
        vec1 = MagicMock()
        vec1.values = [0.1, 0.2]
        vec1.metadata = {"k": "v"}
        vec2 = MagicMock()
        vec2.values = [0.3, 0.4]
        vec2.metadata = None

        mock_index.fetch.return_value = MagicMock(vectors={"v1": vec1, "v2": vec2})

        batches = list(source.extract("my-index", batch_size=10))

        assert len(batches) == 1
        batch, cursor = batches[0]
        assert len(batch) == 2
        assert batch[0].id == "v1"
        assert batch[0].vector == [0.1, 0.2]
        assert batch[0].metadata == {"k": "v"}
        assert batch[0].contents is None
        assert batch[1].id == "v2"

    def test_extract_yields_batch_cursor_tuples(self):
        source = PineconeSource()
        source._client = MagicMock()
        mock_index = MagicMock()
        source._client.Index.return_value = mock_index

        page = MagicMock()
        page.vectors = ["v1"]
        page.pagination = MagicMock()
        page.pagination.next = None
        mock_index.list.return_value = page

        vec1 = MagicMock()
        vec1.values = [0.1]
        vec1.metadata = {}
        mock_index.fetch.return_value = MagicMock(vectors={"v1": vec1})

        for batch, cursor in source.extract("idx", batch_size=10):
            assert isinstance(batch, list)
            # cursor is either str or None
            assert cursor is None or isinstance(cursor, str)
