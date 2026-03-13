from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cyborgdb_migrate.destination import CyborgDestination
    from cyborgdb_migrate.sources.base import SourceConnector


@dataclass
class VectorRecord:
    """Universal vector record that all source connectors produce."""

    id: str
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)
    contents: str | bytes | None = None


@dataclass
class SourceInfo:
    """Summary of what was discovered in the source."""

    source_type: str
    index_or_collection_name: str
    dimension: int
    vector_count: int
    metric: str | None = None
    namespaces: list[str] | None = None
    metadata_fields: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class MigrationResult:
    """Final result of the migration."""

    vectors_migrated: int
    vectors_expected: int
    duration_seconds: float
    spot_check_passed: bool
    spot_check_details: str
    index_name: str


@dataclass
class MigrationState:
    """Shared state passed through all screens.

    Fields are set progressively as the user advances through the wizard.
    Use ready_for_step() to assert that required fields are populated before
    a screen accesses them.
    """

    # Step 1: source selection
    source_connector: SourceConnector | None = None
    # Step 2: source inspection
    source_info: SourceInfo | None = None
    selected_namespace: str | None = None
    # Step 3: CyborgDB connection
    cyborgdb_destination: CyborgDestination | None = None
    existing_indexes: list[str] = field(default_factory=list)
    # Step 4: destination index
    index_name: str | None = None
    index_key: bytes | None = None
    # Options
    batch_size: int = 100
    # Step 6: result
    migration_result: MigrationResult | None = None

    def ready_for_step(self, step: int) -> None:
        """Validate that all fields required by the given step are set."""
        checks: dict[int, list[tuple[str, str]]] = {
            2: [("source_connector", "Source connector not configured")],
            3: [("source_connector", "Source connector not configured")],
            4: [
                ("source_connector", "Source connector not configured"),
                ("source_info", "Source not inspected"),
            ],
            5: [
                ("source_connector", "Source connector not configured"),
                ("source_info", "Source not inspected"),
                ("cyborgdb_destination", "CyborgDB not connected"),
            ],
            6: [
                ("source_connector", "Source connector not configured"),
                ("source_info", "Source not inspected"),
                ("cyborgdb_destination", "CyborgDB not connected"),
                ("index_name", "Destination index not selected"),
                ("index_key", "Encryption key not set"),
            ],
        }
        for attr, msg in checks.get(step, []):
            if getattr(self, attr) is None:
                raise ValueError(msg)
