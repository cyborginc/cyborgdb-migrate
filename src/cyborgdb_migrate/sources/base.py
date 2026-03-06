from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator

from cyborgdb_migrate.models import SourceInfo, VectorRecord


@dataclass
class CredentialField:
    """Describes a single credential field for the TUI to render."""

    key: str
    label: str
    is_secret: bool = False
    default: str | None = None
    required: bool = True
    help_text: str | None = None
    visible_when: dict[str, str] | None = None
    options: list[str] | None = None  # If set, render as radio buttons


class SourceConnector(ABC):
    """Base class for all source connectors."""

    @abstractmethod
    def name(self) -> str:
        """Display name, e.g. 'Pinecone'."""
        ...

    @abstractmethod
    def credential_fields(self) -> list[CredentialField]:
        """Declare what credentials this source needs."""
        ...

    @abstractmethod
    def configure(self, credentials: dict[str, str]) -> None:
        """Receive filled-in credentials. Raise ValueError if invalid."""
        ...

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the source. Raise on failure."""
        ...

    @abstractmethod
    def list_indexes(self) -> list[str]:
        """Return available index/collection names."""
        ...

    @abstractmethod
    def inspect(self, index_name: str) -> SourceInfo:
        """Gather metadata about the selected index."""
        ...

    @abstractmethod
    def extract(
        self,
        index_name: str,
        batch_size: int = 100,
        namespace: str | None = None,
        resume_from: str | None = None,
    ) -> Iterator[tuple[list[VectorRecord], str | None]]:
        """Yield (batch, cursor) tuples from the source."""
        ...
