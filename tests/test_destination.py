from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from cyborgdb_migrate.destination import CyborgDestination, compute_n_lists
from cyborgdb_migrate.models import VectorRecord


class TestComputeNLists:
    def test_small(self):
        assert compute_n_lists(500) == 32

    def test_1k(self):
        assert compute_n_lists(1000) == 128

    def test_medium(self):
        assert compute_n_lists(5000) == 128

    def test_10k(self):
        assert compute_n_lists(10_000) == 512

    def test_large(self):
        assert compute_n_lists(50_000) == 512

    def test_100k(self):
        assert compute_n_lists(100_000) == 1_024

    def test_very_large(self):
        assert compute_n_lists(500_000) == 1_024

    def test_million(self):
        assert compute_n_lists(1_000_000) == 4_096

    def test_huge(self):
        assert compute_n_lists(10_000_000) == 4_096


class TestCyborgDestination:
    def _make_dest(self):
        dest = CyborgDestination()
        dest._client = MagicMock()
        dest._index = MagicMock()
        dest._index_name = "test-index"
        return dest

    @patch("cyborgdb_migrate.destination.Client")
    def test_connect(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        dest = CyborgDestination()
        dest.connect("http://localhost:8000", "api-key")

        mock_client_cls.assert_called_once_with(base_url="http://localhost:8000", api_key="api-key")
        mock_client.get_health.assert_called_once()

    def test_list_indexes(self):
        dest = self._make_dest()
        dest._client.list_indexes.return_value = ["idx1", "idx2"]
        assert dest.list_indexes() == ["idx1", "idx2"]

    @patch("cyborgdb_migrate.destination.IndexIVFFlat")
    def test_create_index_ivfflat(self, mock_config_cls):
        dest = self._make_dest()
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config
        mock_index = MagicMock()
        dest._client.create_index.return_value = mock_index

        dest.create_index("my-idx", 768, "ivfflat", b"k" * 32)

        mock_config_cls.assert_called_once_with(dimension=768)
        dest._client.create_index.assert_called_once_with(
            index_name="my-idx",
            index_key=b"k" * 32,
            index_config=mock_config,
        )
        assert dest._index == mock_index

    @patch("cyborgdb_migrate.destination.IndexIVFPQ")
    def test_create_index_ivfpq(self, mock_config_cls):
        dest = self._make_dest()
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config
        dest._client.create_index.return_value = MagicMock()

        dest.create_index("my-idx", 1536, "ivfpq", b"k" * 32)

        mock_config_cls.assert_called_once_with(dimension=1536, pq_dim=192, pq_bits=8)

    @patch("cyborgdb_migrate.destination.IndexIVFPQ")
    def test_create_index_ivfpq_small_dim(self, mock_config_cls):
        dest = self._make_dest()
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config
        dest._client.create_index.return_value = MagicMock()

        dest.create_index("my-idx", 32, "ivfpq", b"k" * 32)

        # pq_dim should be clamped to min 8
        mock_config_cls.assert_called_once_with(dimension=32, pq_dim=8, pq_bits=8)

    @patch("cyborgdb_migrate.destination.IndexIVF")
    def test_create_index_ivf(self, mock_config_cls):
        dest = self._make_dest()
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config
        dest._client.create_index.return_value = MagicMock()

        dest.create_index("my-idx", 128, "ivf", b"k" * 32)

        mock_config_cls.assert_called_once_with(dimension=128)

    def test_create_index_unknown_type(self):
        dest = self._make_dest()
        with pytest.raises(ValueError, match="Unknown index type"):
            dest.create_index("my-idx", 128, "unknown", b"k" * 32)

    def test_create_index_with_metric(self):
        dest = self._make_dest()
        dest._client.create_index.return_value = MagicMock()

        with patch("cyborgdb_migrate.destination.IndexIVFFlat"):
            dest.create_index("my-idx", 128, "ivfflat", b"k" * 32, metric="cosine")

        call_kwargs = dest._client.create_index.call_args[1]
        assert call_kwargs["metric"] == "cosine"

    def test_load_index(self):
        dest = self._make_dest()
        mock_index = MagicMock()
        dest._client.load_index.return_value = mock_index

        dest.load_index("existing", b"key" * 11)  # 33 bytes, doesn't matter for test

        dest._client.load_index.assert_called_once_with(
            index_name="existing", index_key=b"key" * 11
        )
        assert dest._index == mock_index

    def test_upsert_batch(self):
        dest = self._make_dest()
        records = [
            VectorRecord(id="v1", vector=[0.1, 0.2], metadata={"k": "v"}),
            VectorRecord(id="v2", vector=[0.3, 0.4]),
        ]
        count = dest.upsert_batch(records)

        assert count == 2
        dest._index.upsert.assert_called_once()
        items = dest._index.upsert.call_args[0][0]
        assert items[0]["id"] == "v1"
        assert items[1]["id"] == "v2"
        np.testing.assert_array_almost_equal(items[0]["vector"], np.array([0.1, 0.2], dtype=np.float32))
        np.testing.assert_array_almost_equal(items[1]["vector"], np.array([0.3, 0.4], dtype=np.float32))
        assert items[0]["metadata"] == {"k": "v"}
        assert "metadata" not in items[1]

    def test_upsert_batch_empty(self):
        dest = self._make_dest()
        assert dest.upsert_batch([]) == 0
        dest._index.upsert.assert_not_called()

    def test_upsert_batch_with_contents(self):
        dest = self._make_dest()
        records = [
            VectorRecord(id="v1", vector=[0.1], contents="hello"),
            VectorRecord(id="v2", vector=[0.2], contents=None),
        ]
        dest.upsert_batch(records)

        items = dest._index.upsert.call_args[0][0]
        assert items[0]["contents"] == "hello"
        assert "contents" not in items[1]

    def test_get_count(self):
        dest = self._make_dest()
        dest._index.list_ids.return_value = ["a", "b", "c"]
        assert dest.get_count() == 3

    def test_fetch_by_ids(self):
        dest = self._make_dest()
        dest._index.get.return_value = [
            {"id": "v1", "vector": [0.1, 0.2], "metadata": {"k": "v"}, "contents": "txt"},
            {"id": "v2", "vector": [0.3, 0.4], "metadata": {}, "contents": None},
        ]
        records = dest.fetch_by_ids(["v1", "v2"])
        assert len(records) == 2
        assert records[0].id == "v1"
        assert records[0].vector == [0.1, 0.2]
        assert records[0].metadata == {"k": "v"}
        assert records[0].contents == "txt"
        assert records[1].contents is None

    def test_get_index_dimension(self):
        dest = self._make_dest()
        dest._index.index_config = {"dimension": 768, "type": "ivfflat"}
        assert dest.get_index_dimension() == 768

    def test_get_index_dimension_missing(self):
        dest = self._make_dest()
        dest._index.index_config = {"type": "ivfflat"}
        assert dest.get_index_dimension() is None

    def test_get_index_dimension_error(self):
        dest = self._make_dest()
        type(dest._index).index_config = property(lambda self: (_ for _ in ()).throw(RuntimeError))
        assert dest.get_index_dimension() is None
