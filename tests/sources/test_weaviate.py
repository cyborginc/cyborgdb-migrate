import sys
from unittest.mock import MagicMock, patch

import pytest

from cyborgdb_migrate.sources.weaviate import WeaviateSource


class TestWeaviateCredentials:
    def test_credential_fields(self):
        source = WeaviateSource()
        fields = source.credential_fields()
        assert len(fields) == 2
        assert fields[0].key == "host"
        assert fields[1].key == "api_key"
        assert fields[1].required is False

    def test_configure(self):
        source = WeaviateSource()
        source.configure({"host": "http://weaviate:8080"})
        assert source._host == "http://weaviate:8080"
        assert source._api_key is None

    def test_configure_empty_host(self):
        source = WeaviateSource()
        with pytest.raises(ValueError, match="host"):
            source.configure({"host": ""})

    def test_name(self):
        assert WeaviateSource().name() == "Weaviate"


class TestWeaviateConnect:
    def test_connect_without_api_key(self):
        mock_weaviate_mod = MagicMock()
        mock_auth_mod = MagicMock()

        source = WeaviateSource()
        source._host = "http://localhost:8080"
        source._api_key = None

        with patch.dict(
            sys.modules,
            {"weaviate": mock_weaviate_mod, "weaviate.auth": mock_auth_mod},
        ):
            source.connect()

        mock_weaviate_mod.connect_to_custom.assert_called_once()
        call_kwargs = mock_weaviate_mod.connect_to_custom.call_args[1]
        assert call_kwargs["http_host"] == "localhost"
        assert call_kwargs["http_port"] == 8080
        assert call_kwargs["http_secure"] is False
        assert "auth_credentials" not in call_kwargs

    def test_connect_with_api_key(self):
        mock_weaviate_mod = MagicMock()
        mock_auth_mod = MagicMock()

        source = WeaviateSource()
        source._host = "https://cloud.weaviate.io:443"
        source._api_key = "wv-key"

        with patch.dict(
            sys.modules,
            {"weaviate": mock_weaviate_mod, "weaviate.auth": mock_auth_mod},
        ):
            source.connect()

        mock_weaviate_mod.connect_to_custom.assert_called_once()
        call_kwargs = mock_weaviate_mod.connect_to_custom.call_args[1]
        assert call_kwargs["http_secure"] is True
        assert "auth_credentials" in call_kwargs


class TestWeaviateInspect:
    def test_inspect(self):
        source = WeaviateSource()
        source._client = MagicMock()

        mock_collection = MagicMock()
        source._client.collections.get.return_value = mock_collection

        # Aggregation
        agg = MagicMock()
        agg.total_count = 1000
        mock_collection.aggregate.over_all.return_value = agg

        # Config with properties
        config = MagicMock()
        prop1 = MagicMock()
        prop1.name = "title"
        prop2 = MagicMock()
        prop2.name = "category"
        config.properties = [prop1, prop2]
        config.vector_index_config = MagicMock()
        config.vector_index_config.distance = "cosine"
        mock_collection.config.get.return_value = config

        # Iterator for dimension sampling
        item = MagicMock()
        item.vector = [0.1] * 384
        mock_collection.iterator.return_value = iter([item])

        info = source.inspect("Article")
        assert info.source_type == "weaviate"
        assert info.dimension == 384
        assert info.vector_count == 1000
        assert info.namespaces is None
        assert "title" in info.metadata_fields


class TestWeaviateExtract:
    def test_extract_batching(self):
        source = WeaviateSource()
        source._client = MagicMock()

        mock_collection = MagicMock()
        source._client.collections.get.return_value = mock_collection

        items = []
        for i in range(5):
            item = MagicMock()
            item.uuid = f"uuid-{i}"
            item.vector = [float(i)] * 3
            item.properties = {"title": f"Item {i}"}
            items.append(item)

        mock_collection.iterator.return_value = iter(items)

        batches = list(source.extract("Collection", batch_size=3))
        assert len(batches) == 2
        assert len(batches[0][0]) == 3
        assert len(batches[1][0]) == 2
        assert batches[0][0][0].id == "uuid-0"
        assert batches[0][0][0].contents is None
