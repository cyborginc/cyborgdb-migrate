import pytest

from cyborgdb_migrate.models import (
    MigrationResult,
    MigrationState,
    SourceInfo,
    VectorRecord,
)


class TestVectorRecord:
    def test_basic_construction(self):
        rec = VectorRecord(id="v1", vector=[0.1, 0.2, 0.3])
        assert rec.id == "v1"
        assert rec.vector == [0.1, 0.2, 0.3]
        assert rec.metadata == {}
        assert rec.contents is None

    def test_with_metadata_and_contents(self):
        rec = VectorRecord(
            id="v2",
            vector=[1.0],
            metadata={"key": "val"},
            contents="hello",
        )
        assert rec.metadata == {"key": "val"}
        assert rec.contents == "hello"

    def test_contents_bytes(self):
        rec = VectorRecord(id="v3", vector=[0.0], contents=b"\x00\x01")
        assert rec.contents == b"\x00\x01"


class TestSourceInfo:
    def test_basic_construction(self):
        info = SourceInfo(
            source_type="pinecone",
            index_or_collection_name="my-index",
            dimension=1536,
            vector_count=10000,
        )
        assert info.source_type == "pinecone"
        assert info.dimension == 1536
        assert info.vector_count == 10000
        assert info.metric is None
        assert info.namespaces is None
        assert info.metadata_fields == []
        assert info.extra == {}

    def test_with_all_fields(self):
        info = SourceInfo(
            source_type="qdrant",
            index_or_collection_name="collection1",
            dimension=768,
            vector_count=5000,
            metric="cosine",
            namespaces=["ns1", "ns2"],
            metadata_fields=["field1", "field2"],
            extra={"foo": "bar"},
        )
        assert info.namespaces == ["ns1", "ns2"]
        assert info.metric == "cosine"
        assert info.extra == {"foo": "bar"}


class TestMigrationResult:
    def test_construction(self):
        result = MigrationResult(
            vectors_migrated=1000,
            vectors_expected=1000,
            duration_seconds=12.5,
            spot_check_passed=True,
            spot_check_details="100/100 verified",
            index_name="my-index",
        )
        assert result.vectors_migrated == 1000
        assert result.spot_check_passed is True
        assert result.index_name == "my-index"


class TestMigrationState:
    def test_default_state(self):
        state = MigrationState()
        assert state.source_connector is None
        assert state.batch_size == 100

    def test_ready_for_step_1(self):
        state = MigrationState()
        # Step 1 has no prerequisites
        state.ready_for_step(1)

    def test_ready_for_step_2_fails(self):
        state = MigrationState()
        with pytest.raises(ValueError, match="Source connector not configured"):
            state.ready_for_step(2)

    def test_ready_for_step_3_fails_no_source(self):
        state = MigrationState()
        with pytest.raises(ValueError, match="Source connector not configured"):
            state.ready_for_step(3)

    def test_ready_for_step_4_fails_no_info(self):
        state = MigrationState()
        state.source_connector = "mock"  # type: ignore
        with pytest.raises(ValueError, match="Source not inspected"):
            state.ready_for_step(4)

    def test_ready_for_step_5_fails(self):
        state = MigrationState()
        state.source_connector = "mock"  # type: ignore
        state.source_info = SourceInfo(
            source_type="test", index_or_collection_name="idx", dimension=128, vector_count=100
        )
        with pytest.raises(ValueError, match="CyborgDB not connected"):
            state.ready_for_step(5)

    def test_ready_for_step_6_fails_no_key(self):
        state = MigrationState()
        state.source_connector = "mock"  # type: ignore
        state.source_info = SourceInfo(
            source_type="test", index_or_collection_name="idx", dimension=128, vector_count=100
        )
        state.cyborgdb_destination = "mock"  # type: ignore
        state.index_name = "dest-index"
        with pytest.raises(ValueError, match="Encryption key not set"):
            state.ready_for_step(6)

    def test_ready_for_step_6_passes(self):
        state = MigrationState()
        state.source_connector = "mock"  # type: ignore
        state.source_info = SourceInfo(
            source_type="test", index_or_collection_name="idx", dimension=128, vector_count=100
        )
        state.cyborgdb_destination = "mock"  # type: ignore
        state.index_name = "dest-index"
        state.index_key = b"0" * 32
        state.ready_for_step(6)
