import sys
from unittest.mock import MagicMock, patch

import pytest

from cyborgdb_migrate.sources.milvus import MilvusSource


class TestMilvusCredentials:
    def test_credential_fields(self):
        source = MilvusSource()
        fields = source.credential_fields()
        assert len(fields) == 3
        keys = [f.key for f in fields]
        assert "uri" in keys
        assert "token" in keys
        assert "database" in keys
        assert fields[1].required is False  # token is optional

    def test_configure(self):
        source = MilvusSource()
        source.configure({"uri": "http://milvus:19530", "token": "tk-123", "database": "mydb"})
        assert source._uri == "http://milvus:19530"
        assert source._token == "tk-123"
        assert source._database == "mydb"

    def test_configure_empty_uri(self):
        source = MilvusSource()
        with pytest.raises(ValueError, match="URI"):
            source.configure({"uri": ""})

    def test_name(self):
        assert MilvusSource().name() == "Milvus"


class TestMilvusConnect:
    def test_connect(self):
        mock_cls = MagicMock()
        mock_mod = MagicMock()
        mock_mod.MilvusClient = mock_cls

        source = MilvusSource()
        source._uri = "http://localhost:19530"
        source._token = None
        source._database = "default"

        with patch.dict(sys.modules, {"pymilvus": mock_mod}):
            source.connect()

        mock_cls.assert_called_once_with(uri="http://localhost:19530", db_name="default")

    def test_connect_with_token(self):
        mock_cls = MagicMock()
        mock_mod = MagicMock()
        mock_mod.MilvusClient = mock_cls

        source = MilvusSource()
        source._uri = "http://zilliz.cloud"
        source._token = "my-token"
        source._database = "db1"

        with patch.dict(sys.modules, {"pymilvus": mock_mod}):
            source.connect()

        mock_cls.assert_called_once_with(
            uri="http://zilliz.cloud", token="my-token", db_name="db1"
        )


class TestMilvusInspect:
    def test_inspect(self):
        source = MilvusSource()
        source._client = MagicMock()

        # describe_collection returns fields
        source._client.describe_collection.return_value = {
            "fields": [
                {"name": "id", "type": 5, "is_primary": True},
                {"name": "embedding", "type": 101, "params": {"dim": "768"}},
                {"name": "title", "type": 21, "params": {"max_length": "100"}},
                {"name": "content", "type": 21, "params": {"max_length": "5000"}},
            ]
        }

        source._client.get_collection_stats.return_value = {"row_count": 10000}
        source._client.list_partitions.return_value = ["_default"]
        source._client.list_indexes.return_value = ["idx1"]
        source._client.describe_index.return_value = {"metric_type": "COSINE"}

        info = source.inspect("my-collection")
        assert info.source_type == "milvus"
        assert info.dimension == 768
        assert info.vector_count == 10000
        assert info.metric == "cosine"
        assert info.namespaces is None  # Only _default partition
        assert info.extra["vector_field"] == "embedding"
        assert info.extra["content_field"] == "content"  # Matches heuristic

    def test_inspect_with_partitions(self):
        source = MilvusSource()
        source._client = MagicMock()

        source._client.describe_collection.return_value = {
            "fields": [
                {"name": "pk", "type": 5, "is_primary": True},
                {"name": "vec", "type": 101, "params": {"dim": "128"}},
            ]
        }
        source._client.get_collection_stats.return_value = {"row_count": 5000}
        source._client.list_partitions.return_value = ["_default", "part1", "part2"]
        source._client.list_indexes.return_value = []

        info = source.inspect("col")
        assert info.namespaces == ["_default", "part1", "part2"]


class TestMilvusExtract:
    def test_extract(self):
        source = MilvusSource()
        source._client = MagicMock()

        # Mock inspect for field discovery
        source._client.describe_collection.return_value = {
            "fields": [
                {"name": "id", "type": 5, "is_primary": True},
                {"name": "vector", "type": 101, "params": {"dim": "3"}},
                {"name": "title", "type": 21, "params": {"max_length": "100"}},
            ]
        }
        source._client.get_collection_stats.return_value = {"row_count": 2}
        source._client.list_partitions.return_value = ["_default"]
        source._client.list_indexes.return_value = []

        # Mock query
        source._client.query.side_effect = [
            [
                {"id": "1", "vector": [0.1, 0.2, 0.3], "title": "Item 1"},
                {"id": "2", "vector": [0.4, 0.5, 0.6], "title": "Item 2"},
            ],
            [],
        ]

        batches = list(source.extract("col", batch_size=10))
        assert len(batches) == 1
        batch, cursor = batches[0]
        assert len(batch) == 2
        assert batch[0].id == "1"
        assert batch[0].vector == [0.1, 0.2, 0.3]
        assert batch[0].metadata == {"title": "Item 1"}
        assert cursor == "2"

    def test_extract_with_content_field(self):
        source = MilvusSource()
        source._client = MagicMock()

        source._client.describe_collection.return_value = {
            "fields": [
                {"name": "id", "type": 5, "is_primary": True},
                {"name": "vec", "type": 101, "params": {"dim": "2"}},
                {"name": "text", "type": 21, "params": {"max_length": "1000"}},
            ]
        }
        source._client.get_collection_stats.return_value = {"row_count": 1}
        source._client.list_partitions.return_value = ["_default"]
        source._client.list_indexes.return_value = []

        source._client.query.side_effect = [
            [{"id": "1", "vec": [0.1, 0.2], "text": "Hello world"}],
            [],
        ]

        batches = list(source.extract("col", batch_size=10))
        batch, _ = batches[0]
        # "text" should be mapped to contents via heuristic
        assert batch[0].contents == "Hello world"
        assert "text" not in batch[0].metadata
