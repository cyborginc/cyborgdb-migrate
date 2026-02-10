# PRD: CyborgDB Migration Tool (TUI Wizard)

## Overview

A Python-based terminal UI (TUI) wizard that guides users through migrating vector data from other vector databases into CyborgDB. The tool should feel polished, opinionated-by-default, and hard to misuse. It supports both interactive wizard mode (default) and non-interactive/scripted mode via config file.

The tool migrates **one index/collection at a time**. For sources with namespaces or partitions, the user selects a single namespace per run. Run the tool multiple times to migrate multiple namespaces or indexes.

The tool is called `cyborgdb-migrate`.

---

## Goals

1. **One-command migration**: A user with vectors in Pinecone, Qdrant, Weaviate, ChromaDB, or Milvus should be able to run `cyborgdb-migrate` and have their data in CyborgDB within minutes.
2. **Safe by default**: The encryption key flow must be impossible to skip or ignore. The user must explicitly acknowledge they've saved their key.
3. **Resumable**: Large migrations should survive interruptions. Checkpoint state after every N batches.
4. **Verifiable**: After migration, spot-check a random sample of vectors (cached during extraction) to confirm data integrity.
5. **Extensible**: Adding a new source connector should require implementing a single well-defined interface, with no changes to the core migration engine or TUI.

---

## Non-Goals

- Real-time sync or CDC (change data capture). This is a one-time migration tool.
- Transforming embeddings (re-embedding with a different model). Vectors are copied as-is.
- Managing CyborgDB infrastructure (backing store setup, deployment, etc.).
- Multi-namespace migration in a single run. Run the tool once per namespace.

---

## Technical Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.10+ | Matches CyborgDB's primary SDK language |
| TUI framework | `textual` | Full-screen TUI framework from Textualize. Actively maintained, funded company. Screen-based architecture maps naturally to wizard steps. Rich widget library (inputs, selects, progress bars, data tables) in one package. Built-in CSS-like theming. Future-proof for adding post-migration features (index browser, dashboard). |
| CLI entry point | `argparse` (stdlib) | Thin wrapper for `--config`, `--resume`, `--batch-size`, `--log-file` flags. Launches the Textual app in interactive mode or runs headless in non-interactive mode. No external dependency needed for a single command with a few flags. |
| Config format | TOML | For non-interactive mode config files. Built into Python 3.11+ (`tomllib`), use `tomli` backport for 3.10. |
| Packaging | Standard `pyproject.toml` with `pip install cyborgdb-migrate` |

**Note on Textual:** Textual uses `rich` internally for rendering, so all of rich's formatting (styled text, tables, panels) is available within Textual widgets via the `Static` widget and `Rich` renderables. There is no need to install `rich` separately.

### Key Dependencies (Source Connectors)

| Source | Python Client |
|--------|--------------|
| Pinecone | `pinecone` (official SDK, grpc variant preferred) |
| Qdrant | `qdrant-client` |
| Weaviate | `weaviate-client` |
| ChromaDB | `chromadb` |
| Milvus | `pymilvus` |
| CyborgDB (destination) | `cyborgdb` (service client SDK) |

---

## Architecture

### Project Structure

```
cyborgdb-migrate/
├── pyproject.toml
├── README.md
├── src/
│   └── cyborgdb_migrate/
│       ├── __init__.py
│       ├── cli.py                  # argparse entry point — launches Textual app or headless mode
│       ├── app.py                  # Textual App subclass — root of the TUI, manages screen stack
│       ├── theme.css               # Textual CSS — colors, spacing, widget styles
│       ├── screens/
│       │   ├── __init__.py
│       │   ├── source_select.py    # Step 1: Pick source DB + enter credentials
│       │   ├── source_inspect.py   # Step 2: Pick index + namespace, view summary
│       │   ├── cyborgdb_connect.py # Step 3: Connect to CyborgDB
│       │   ├── dest_index.py       # Step 4: Create or select destination index + encryption key
│       │   ├── migrate.py          # Step 5: Live migration progress
│       │   └── summary.py          # Step 6: Verification results + quickstart snippet
│       ├── widgets/
│       │   ├── __init__.py
│       │   ├── step_header.py      # Reusable "Step X of 6" header bar
│       │   ├── key_warning.py      # Encryption key warning modal
│       │   └── source_form.py      # Dynamic credential form (fields vary per source)
│       ├── engine.py               # Core migration engine (batch stream, checkpoint, verify)
│       ├── models.py               # Shared data models (VectorRecord, SourceInfo, etc.)
│       ├── destination.py          # CyborgDB destination handler (create index, upsert, verify)
│       ├── config.py               # TOML config loader for non-interactive mode (with env var expansion)
│       ├── checkpoint.py           # Checkpoint/resume logic
│       └── sources/
│           ├── __init__.py         # Source registry + base class
│           ├── base.py             # Abstract base class for all source connectors
│           ├── pinecone.py
│           ├── qdrant.py
│           ├── weaviate.py
│           ├── chromadb.py
│           └── milvus.py
└── tests/
    ├── test_engine.py
    ├── test_checkpoint.py
    ├── test_config.py               # Test env var expansion in TOML config
    ├── test_app.py                  # Textual pilot tests for screen flow
    └── sources/
        ├── test_pinecone.py
        ├── test_qdrant.py
        ├── test_weaviate.py
        ├── test_chromadb.py
        └── test_milvus.py
```

### Textual App Structure (`app.py`)

The app uses Textual's screen stack to push/pop wizard steps. A shared state object is passed between screens.

```python
from dataclasses import dataclass, field
from textual.app import App
from cyborgdb_migrate.screens.source_select import SourceSelectScreen

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
    selected_namespace: str | None = None     # Single namespace (or None if source has no namespaces)
    # Step 3: CyborgDB connection
    cyborgdb_destination: CyborgDestination | None = None
    # Step 4: destination index
    index_name: str | None = None
    index_key: bytes | None = None
    key_file_path: str | None = None
    # Options
    batch_size: int = 100
    # Step 6: result
    migration_result: MigrationResult | None = None

    def ready_for_step(self, step: int) -> None:
        """Assert that all fields required by the given step are set.
        Raises AssertionError with a clear message if not.
        """
        checks: dict[int, list[tuple[str, str]]] = {
            2: [("source_connector", "Source connector not configured")],
            3: [("source_connector", "Source connector not configured"),
                ("source_info", "Source not inspected")],
            4: [("source_connector", "Source connector not configured"),
                ("source_info", "Source not inspected"),
                ("cyborgdb_destination", "CyborgDB not connected")],
            5: [("source_connector", "Source connector not configured"),
                ("source_info", "Source not inspected"),
                ("cyborgdb_destination", "CyborgDB not connected"),
                ("index_name", "Destination index not selected"),
                ("index_key", "Encryption key not set")],
        }
        for attr, msg in checks.get(step, []):
            assert getattr(self, attr) is not None, msg

class MigrateApp(App):
    CSS_PATH = "theme.css"
    TITLE = "CyborgDB Migration Wizard"

    def __init__(self, state: MigrationState | None = None):
        super().__init__()
        self.state = state or MigrationState()

    def on_mount(self) -> None:
        self.push_screen(SourceSelectScreen(self.state))
```

Each screen receives `self.state`, calls `state.ready_for_step(N)` on mount, mutates state, and pushes the next screen. Screens can also pop themselves to go back.

### Core Data Model (`models.py`)

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class VectorRecord:
    """Universal vector record that all source connectors produce."""
    id: str
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)
    contents: str | bytes | None = None   # Optional: maps to CyborgDB's contents parameter on upsert.
                                           # ChromaDB: populated from documents field.
                                           # Milvus: populated from VARCHAR fields that appear to be document content.
                                           # Pinecone, Qdrant, Weaviate: leave as None (no equivalent concept).

@dataclass
class SourceInfo:
    """Summary of what was discovered in the source."""
    source_type: str                    # "pinecone", "qdrant", etc.
    index_or_collection_name: str
    dimension: int
    vector_count: int
    metric: str | None = None           # "cosine", "euclidean", "dotproduct", etc.
    namespaces: list[str] | None = None # Pinecone namespaces, Milvus partitions, etc. None if source has no namespace concept.
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
    key_file_path: str | None = None
```

### Source Connector Interface (`sources/base.py`)

Source connectors are pure data layer — they know nothing about the UI. Each connector declares what credential fields it needs, and the TUI renders the form dynamically.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator
from cyborgdb_migrate.models import VectorRecord, SourceInfo

@dataclass
class CredentialField:
    """Describes a single credential field for the TUI to render."""
    key: str                            # Internal key, e.g. "api_key"
    label: str                          # Display label, e.g. "API Key"
    is_secret: bool = False             # If True, render as password input
    default: str | None = None          # Default value (shown as placeholder)
    required: bool = True
    help_text: str | None = None        # Tooltip / helper text below the field
    visible_when: dict[str, str] | None = None  # Conditional visibility: {"field_key": "value"}.
                                                 # Only shown when the referenced field has the given value.
                                                 # Used by ChromaDB to show path vs host+port based on mode.

class SourceConnector(ABC):
    """Base class for all source connectors."""

    @abstractmethod
    def name(self) -> str:
        """Display name, e.g. 'Pinecone'."""
        ...

    @abstractmethod
    def credential_fields(self) -> list[CredentialField]:
        """
        Declare what credentials this source needs.
        The TUI will render an Input widget for each field.
        Example for Pinecone: [CredentialField(key="api_key", label="API Key", is_secret=True)]
        Example for Qdrant:   [CredentialField(key="host", label="Host URL", default="http://localhost:6333"),
                                CredentialField(key="api_key", label="API Key", is_secret=True, required=False)]
        """
        ...

    @abstractmethod
    def configure(self, credentials: dict[str, str]) -> None:
        """
        Receive filled-in credentials from the TUI (or from TOML config).
        Store them on self. This is the same for interactive and non-interactive mode.
        Raise ValueError if a required field is missing or invalid.
        """
        ...

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the source. Raise on failure."""
        ...

    @abstractmethod
    def list_indexes(self) -> list[str]:
        """Return available index/collection names for the user to pick from."""
        ...

    @abstractmethod
    def inspect(self, index_name: str) -> SourceInfo:
        """
        Gather metadata about the selected index: dimension, count,
        metric, namespaces, metadata field names, etc.
        """
        ...

    @abstractmethod
    def extract(
        self,
        index_name: str,
        batch_size: int = 100,
        namespace: str | None = None,
        resume_from: str | None = None,
    ) -> Iterator[tuple[list[VectorRecord], str | None]]:
        """
        Yield (batch, cursor) tuples from the source.
        - batch: list of up to batch_size VectorRecords
        - cursor: opaque string representing current extraction position (for checkpointing).
                  None if the source doesn't support cursors.
        - namespace: single namespace/partition to read from (None if source has no namespace concept)
        - resume_from: opaque cursor string to resume from (from checkpoint)

        The iterator should handle pagination internally.
        """
        ...
```

**Key design decision:** Connectors declare their fields via `credential_fields()` and receive filled values via `configure(credentials)`. This decouples the data layer from the UI — the same connector works for both the Textual TUI and headless/non-interactive mode with zero branching. The `extract()` method yields `(batch, cursor)` tuples, making the checkpoint relationship explicit and eliminating the need for a separate stateful `get_cursor()` call.

### Source Registration

Source connectors are registered in `sources/__init__.py`:

```python
from cyborgdb_migrate.sources.pinecone import PineconeSource
from cyborgdb_migrate.sources.qdrant import QdrantSource
from cyborgdb_migrate.sources.weaviate import WeaviateSource
from cyborgdb_migrate.sources.chromadb import ChromaDBSource
from cyborgdb_migrate.sources.milvus import MilvusSource

SOURCE_REGISTRY: dict[str, type] = {
    "Pinecone": PineconeSource,
    "Qdrant": QdrantSource,
    "Weaviate": WeaviateSource,
    "ChromaDB": ChromaDBSource,
    "Milvus": MilvusSource,
}
```

---

## Textual Theming (`theme.css`)

Define a consistent visual style across all screens. Use CyborgDB brand colors if available, otherwise a clean dark theme.

```css
/* Global */
Screen {
    background: $surface;
}

/* Step header bar — shows "Step X of 6: Title" */
.step-header {
    dock: top;
    height: 3;
    background: $primary;
    color: $text;
    text-align: center;
    text-style: bold;
    padding: 1;
}

/* Main content area */
.step-content {
    padding: 1 2;
}

/* Summary panels */
.summary-panel {
    border: round $accent;
    padding: 1 2;
    margin: 1 0;
}

/* Warning panels (encryption key) */
.warning-panel {
    border: heavy $warning;
    background: $warning 10%;
    padding: 1 2;
    margin: 1 0;
}

/* Action buttons row */
.button-row {
    dock: bottom;
    height: 3;
    align: right middle;
    padding: 0 2;
}

/* Progress area */
.progress-container {
    padding: 1 2;
}
```

---

## Interactive Wizard Flow (Screens)

The wizard is the default mode. Each step is a Textual `Screen` subclass. Screens are pushed onto the app's screen stack. The user can go forward (push next screen) or back (pop current screen). All screens share a `MigrationState` object.

Every screen has:
- A `StepHeader` widget at the top showing "Step X of 6: {title}" with a progress indicator.
- A content area in the middle.
- A button row at the bottom with "Back" and "Next" (or "Start Migration", "Done", etc.).

### Screen 1: SourceSelectScreen (`screens/source_select.py`)

**Layout:**

```
┌────────────────────────────────────────────────────┐
│  Step 1 of 6: Select Source                        │
├────────────────────────────────────────────────────┤
│                                                    │
│  Where are you migrating from?                     │
│                                                    │
│  ┌──────────────────────────────────────────────┐  │
│  │  ❯ Pinecone                                  │  │
│  │    Qdrant                                    │  │
│  │    Weaviate                                  │  │
│  │    ChromaDB                                  │  │
│  │    Milvus                                    │  │
│  └──────────────────────────────────────────────┘  │
│                                                    │
│  ── Pinecone Credentials ──────────────────────    │
│                                                    │
│  API Key: [●●●●●●●●●●●●●●●●●●●]                   │
│                                                    │
│                                                    │
├────────────────────────────────────────────────────┤
│                              [Connect & Continue]  │
└────────────────────────────────────────────────────┘
```

**Widgets:**
- `OptionList` — populated from `SOURCE_REGISTRY.keys()`. When the user highlights a source, the credential form below updates dynamically.
- `SourceForm` (custom widget in `widgets/source_form.py`) — reads `source.credential_fields()` and renders an `Input` widget for each field (with `password=True` for secrets). This form updates live as the user switches sources. Fields with `visible_when` are shown/hidden reactively based on other field values.
- "Connect & Continue" `Button` — calls `source.configure(credentials)` then `source.connect()` in a Textual `Worker` (background thread). Shows a `LoadingIndicator` while connecting. On success, pushes `SourceInspectScreen`. On failure, shows an inline error notification with the error message and lets the user correct credentials and retry.

**Textual implementation notes:**
- Use `@work(thread=True)` decorator for the `connect()` call since it's blocking I/O. Post a message to the screen on completion/failure.
- The credential form is rebuilt via `source_form.rebuild(source.credential_fields())` when the source selection changes.

### Screen 2: SourceInspectScreen (`screens/source_inspect.py`)

**Layout:**

```
┌────────────────────────────────────────────────────┐
│  Step 2 of 6: Select Data                          │
├────────────────────────────────────────────────────┤
│                                                    │
│  Select an index to migrate:                       │
│                                                    │
│  ┌──────────────────────────────────────────────┐  │
│  │  ❯ product-embeddings  (1536d, 142,387 vec)  │  │
│  │    search-index        (768d, 12,001 vec)    │  │
│  └──────────────────────────────────────────────┘  │
│                                                    │
│  Select a namespace:                               │
│  ┌──────────────────────────────────────────────┐  │
│  │  ❯ default          (98,210 vectors)         │  │
│  │    products         (32,104 vectors)         │  │
│  │    categories       (12,073 vectors)         │  │
│  └──────────────────────────────────────────────┘  │
│                                                    │
│  ┌─ Source Summary ────────────────────────────┐   │
│  │  Source:     Pinecone                       │   │
│  │  Index:      product-embeddings             │   │
│  │  Namespace:  default                        │   │
│  │  Dimension:  1536                           │   │
│  │  Vectors:    98,210                         │   │
│  │  Metadata:   category, sku, price           │   │
│  └─────────────────────────────────────────────┘   │
│                                                    │
├────────────────────────────────────────────────────┤
│  [Back]                               [Continue]   │
└────────────────────────────────────────────────────┘
```

**Widgets:**
- `OptionList` for index selection — populated by calling `source.list_indexes()` in a worker. Show a `LoadingIndicator` while fetching. Each item shows the index name plus dimension and vector count.
- Namespace `OptionList` — **only shown if `source_info.namespaces` is not None and has more than one entry.** If the source has no namespace concept (or only one namespace), skip this entirely. The user selects exactly one namespace. The vector count shown in the summary reflects the selected namespace's count, not the full index.
- `Static` widget rendering a `rich.panel.Panel` with the source summary table. This updates reactively when the user changes index or namespace selections.
- "Back" button pops this screen. "Continue" pushes `CyborgConnectScreen`.

**Textual implementation notes:**
- When the user selects an index, call `source.inspect(index_name)` in a worker. Update the summary panel on completion. The "Continue" button should be disabled until inspection completes.
- If the source has multiple namespaces, the namespace list is shown after inspection completes. The summary panel updates when the user selects a namespace.

### Screen 3: CyborgConnectScreen (`screens/cyborgdb_connect.py`)

**Layout:**

```
┌────────────────────────────────────────────────────┐
│  Step 3 of 6: CyborgDB Connection                  │
├────────────────────────────────────────────────────┤
│                                                    │
│  CyborgDB host URL: [https://localhost:8000    ]   │
│  CyborgDB API key:  [●●●●●●●●●●●●●●●●●●●●●●●●]   │
│                                                    │
│                                                    │
│                                                    │
│                                                    │
├────────────────────────────────────────────────────┤
│  [Back]                       [Connect & Continue] │
└────────────────────────────────────────────────────┘
```

**Widgets:**
- Two `Input` widgets — host URL (with default `https://localhost:8000`) and API key (with `password=True`).
- "Connect & Continue" `Button` — calls `destination.connect(host, api_key)` in a worker. On success, shows a `✓ Connected to CyborgDB` notification and pushes `DestIndexScreen`. On failure, shows inline error.

### Screen 4: DestIndexScreen (`screens/dest_index.py`)

This is the most complex screen. It has two paths: create new index or use existing.

**Layout (initial):**

```
┌────────────────────────────────────────────────────┐
│  Step 4 of 6: Destination Index                     │
├────────────────────────────────────────────────────┤
│                                                    │
│  ┌──────────────────────────────────────────────┐  │
│  │  ❯ Create new index                          │  │
│  │    Use existing index                        │  │
│  └──────────────────────────────────────────────┘  │
│                                                    │
│  (form area updates based on selection above)      │
│                                                    │
├────────────────────────────────────────────────────┤
│  [Back]                               [Continue]   │
└────────────────────────────────────────────────────┘
```

**Path A: Create New Index**

When "Create new index" is selected, the form area shows:

- `Input` for index name (default: source index name).
- `RadioSet` for index type with three `RadioButton`s:
  - `IVFFlat` — with label including recommendation based on vector count
  - `IVFPQ` — with label
  - `IVF` — with label
- A `Static` showing the auto-derived config: `Index config: IVFFlat, dimension=1536, n_lists=1024`
- `RadioSet` for encryption key:
  - `Generate a new key (recommended)`
  - `Provide my own key`
- If "Provide my own key": an `Input` for the base64-encoded key.

Index type recommendation logic (shown in radio button labels):
- < 10K vectors → IVFFlat label includes "(recommended for small datasets)"
- 10K - 500K vectors → IVFFlat label includes "(recommended for ~{count} vectors)"
- 500K+ vectors → IVFPQ label includes "(recommended for large datasets)"

On "Continue": if generating a new key, generate it, save to file (`chmod 600`), then show the **KeyWarningModal**. If the key file already exists, prompt the user to choose a different name (interactive) or error (headless). Key files are never silently overwritten.

**KeyWarningModal** (`widgets/key_warning.py`):

This is a Textual `ModalScreen` that overlays the current screen. It MUST be dismissed explicitly.

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│   ⚠  IMPORTANT: Encryption Key                      │
│                                                     │
│   Your encryption key has been saved to:            │
│   ./cyborgdb-migrate-keys/product-embeddings.key    │
│                                                     │
│   SAVE THIS FILE SECURELY.                          │
│   Without this key, your data is permanently        │
│   unrecoverable. CyborgDB cannot recover it.        │
│                                                     │
│   ┌─────────────────────────────────────────────┐   │
│   │ Type "I understand" to continue:            │   │
│   │ [                                         ] │   │
│   └─────────────────────────────────────────────┘   │
│                                                     │
│                          [Cancel]    [Continue]      │
│                                                     │
└─────────────────────────────────────────────────────┘
```

The "Continue" button is **disabled** until the user types exactly "I understand" in the input field. This is stronger than a simple yes/no confirmation — it forces the user to engage with the warning. "Cancel" dismisses the modal without proceeding.

After the modal is dismissed with confirmation, create the index on CyborgDB and push `MigrateScreen`.

**Path B: Use Existing Index**

When "Use existing index" is selected, the form area shows:

- `OptionList` of existing CyborgDB indexes (fetched via worker). Each item shows name, dimension, and index type.
- `Input` for encryption key (with `password=True`).

On "Continue": load the index, validate dimension match against source. If mismatch, show inline error: "Dimension mismatch: source has 1536d, destination has 768d." If index already has vectors, show a warning notification: "This index contains 50,000 vectors. Existing IDs will be overwritten on upsert."

### Screen 5: MigrateScreen (`screens/migrate.py`)

This is where Textual shines. This is a live, full-screen dashboard with real-time updates.

**Layout:**

```
┌────────────────────────────────────────────────────┐
│  Step 5 of 6: Migrating                            │
├────────────────────────────────────────────────────┤
│                                                    │
│  product-embeddings → CyborgDB (product-embeddings)│
│                                                    │
│  ┌─ Progress ─────────────────────────────────┐    │
│  │                                            │    │
│  │  ████████████████████░░░░░  78%            │    │
│  │                                            │    │
│  │  Vectors:  76,600 / 98,210                 │    │
│  │  Batch:    766 / 983                       │    │
│  │  Speed:    ~1,200 vec/s                    │    │
│  │  Elapsed:  3m 18s                          │    │
│  │  ETA:      2m 14s                          │    │
│  │  Errors:   0                               │    │
│  └────────────────────────────────────────────┘    │
│                                                    │
│  ┌─ Log ──────────────────────────────────────┐    │
│  │  14:32:01  Batch 764 upserted (100 vec)    │    │
│  │  14:32:02  Batch 765 upserted (100 vec)    │    │
│  │  14:32:03  Batch 766 upserted (100 vec)    │    │
│  │  14:32:03  Checkpoint saved (766 batches)  │    │
│  │                                            │    │
│  └────────────────────────────────────────────┘    │
│                                                    │
├────────────────────────────────────────────────────┤
│  [Cancel Migration]                                │
└────────────────────────────────────────────────────┘
```

**Widgets:**
- `Static` for the source → destination header.
- `ProgressBar` widget — updated reactively via the engine's progress callback.
- `Static` labels for stats (vectors, batch, speed, ETA, errors) — updated via reactive attributes or message passing.
- `RichLog` widget for the scrollable log panel. Each batch completion, checkpoint save, retry, or error appends a timestamped line. The log auto-scrolls but the user can scroll up to review.
- "Cancel Migration" `Button` — saves checkpoint and stops the migration gracefully.

**Textual implementation notes:**
- The migration runs in a `Worker` thread via `@work(thread=True)`. The engine calls `on_progress` callback which posts `MigrationProgress` messages to the screen. The screen's message handler updates the reactive UI.
- Checkpointing happens in the worker thread (no UI interaction needed).
- On completion, the worker posts a `MigrationComplete` message. The screen handler pushes `SummaryScreen`.
- On fatal error, the worker posts a `MigrationFailed` message. The screen shows the error inline and offers "Retry" or "Exit" buttons.
- "Cancel Migration" sends a cancellation signal to the worker. The engine checks this signal between batches, saves checkpoint, and exits cleanly.

**Checkpoint resume:** Before starting migration, the screen checks for an existing checkpoint file. If found, show a small panel above the progress area:

```
Found checkpoint: 50,000 / 98,210 vectors (51%)
Last updated: 2025-02-10 14:30:22

[Resume]  [Start Fresh]
```

This is displayed inline on the MigrateScreen before the progress widgets, not as a separate screen.

**Batch size**: Default 100. Not a wizard prompt — available via `--batch-size` CLI flag or config file.

**Error handling during migration**:
- Transient errors (network timeout, rate limit): Retry with exponential backoff, up to 3 retries per batch. Log each retry in the RichLog.
- Persistent errors: Log the failed batch IDs in the RichLog, continue with next batch. Increment error counter.
- Fatal errors (auth failure, index deleted): Stop migration, save checkpoint, show error with Retry/Exit options.

### Screen 6: SummaryScreen (`screens/summary.py`)

**Layout:**

```
┌────────────────────────────────────────────────────┐
│  Step 6 of 6: Complete                              │
├────────────────────────────────────────────────────┤
│                                                    │
│  ✓ Count check: 98,210 / 98,210 vectors            │
│  ✓ Spot check: 3,932/3,932 verified (values + metadata)│
│                                                    │
│  ┌─ Migration Complete ───────────────────────┐    │
│  │                                            │    │
│  │  Source:    Pinecone / product-embeddings   │    │
│  │  Dest:     CyborgDB / product-embeddings   │    │
│  │  Vectors:  98,210                          │    │
│  │  Duration: 4m 32s                          │    │
│  │  Key file: ./cyborgdb-migrate-keys/pro...  │    │
│  │                                            │    │
│  └────────────────────────────────────────────┘    │
│                                                    │
│  ┌─ Quick Start ──────────────────────────────┐    │
│  │                                            │    │
│  │  from cyborgdb import Client               │    │
│  │  client = Client(                          │    │
│  │      "https://localhost:8000", api_key     │    │
│  │  )                                         │    │
│  │  index = client.load_index(                │    │
│  │      "product-embeddings", index_key       │    │
│  │  )                                         │    │
│  │  results = index.query(                    │    │
│  │      query_vector=[...], top_k=10          │    │
│  │  )                                         │    │
│  │                                            │    │
│  └────────────────────────────────────────────┘    │
│                                                    │
├────────────────────────────────────────────────────┤
│                                          [Done]    │
└────────────────────────────────────────────────────┘
```

**Widgets:**
- `Static` labels for each verification step (✓ or ✗ with styled colors).
- `Static` rendering a `rich.panel.Panel` for the migration summary.
- `Static` rendering a `rich.syntax.Syntax` (with Python highlighting) for the quickstart code snippet.
- "Done" `Button` — exits the Textual app with exit code 0.

**Before this screen is shown:**
1. Verification runs in a worker: compare counts, spot-check cached vector samples against CyborgDB.
2. A `LoadingIndicator` or spinner is shown while verification runs.
3. Once complete, the full summary is displayed.
4. Checkpoint file is deleted on successful completion.

**Note on training:** CyborgDB handles index training automatically. No explicit training step is needed in V1. See Future Enhancements for V1.5 plans.

---

## Non-Interactive Mode

Invoked with `cyborgdb-migrate --config migration.toml` or with CLI flags.

In non-interactive mode, the Textual app is NOT launched. Instead, `cli.py` runs the migration engine directly with simple `rich` console output (Textual includes rich internally, so this is available without extra deps):

```python
# In cli.py
if config:
    # Parse config (with env var expansion), configure source, connect, run engine
    # Use rich console for progress output (not Textual)
    run_headless(config_path, batch_size, resume, log_file, quiet)
else:
    # Launch Textual app
    app = MigrateApp(state)
    app.run()
```

### TOML Config Format

```toml
[source]
type = "pinecone"
api_key = "${PINECONE_API_KEY}"         # Environment variable expansion — NEVER store plaintext secrets
index = "product-embeddings"
namespace = "default"                    # Single namespace. Omit if source has no namespace concept.

[destination]
host = "${CYBORGDB_HOST}"
api_key = "${CYBORGDB_API_KEY}"

# Either create a new index:
create_index = true
index_name = "product-embeddings"
index_type = "ivfflat"                  # "ivf", "ivfflat", "ivfpq"
key_file = "./my-key.key"              # Path to save generated key, or path to existing key

# Or use an existing index:
# create_index = false
# index_name = "existing-index"
# index_key = "${CYBORGDB_INDEX_KEY}"   # base64-encoded

[options]
batch_size = 100
checkpoint_every = 10                   # batches between checkpoints
verify = true
spot_check_per_batch = 4              # vectors cached per batch for post-migration verification (no cap)
```

**Environment variable expansion:** The config loader expands `${VAR_NAME}` patterns using `os.environ`. If a referenced variable is not set, the loader raises an error with a clear message naming the missing variable. This prevents accidental plaintext secret storage in config files.

In non-interactive mode:
- All prompts are skipped; values come from config.
- Progress is displayed via `rich.progress.Progress` to stdout (unless `--quiet`, in which case output is minimal log lines to stderr).
- The encryption key confirmation is skipped (assumed the user knows what they're doing in scripted mode).
- Errors are logged to stderr and the process exits with a non-zero code.
- Use `--resume` to automatically find and resume from a matching checkpoint file.

---

## Source Connector Specifications

### Pinecone (`sources/pinecone.py`)

**Credential fields:**
```python
def credential_fields(self) -> list[CredentialField]:
    return [
        CredentialField(key="api_key", label="API Key", is_secret=True),
    ]
```

**Connection:** Use `pinecone.Pinecone(api_key=...)`.

**List indexes:** `pc.list_indexes()` — return index names with dimension and vector count.

**Inspect:** `index.describe_index_stats()` — returns dimension, total vector count, and per-namespace counts. Populate `namespaces` in `SourceInfo` with namespace names and counts.

**Extract:**
- Use `index.list()` to paginate through all vector IDs in the selected namespace (returns paginated ID lists).
- Batch fetch with `index.fetch(ids=[...])` to get vectors + metadata.
- Batch size for fetch: up to 1000 IDs per fetch call (Pinecone limit), but yield in `batch_size` chunks to the engine.
- Pagination cursor: Pinecone's `list()` returns a `pagination` token. Yield as the cursor in `(batch, cursor)` tuples.

**Notes:**
- Pinecone fetch does NOT return vectors for on-demand (serverless) indexes by default if they are stored in object storage. Use `include_values=True`.
- Pinecone has a 10-second timeout by default; consider increasing for large fetches.
- `contents`: always None (Pinecone has no document/content concept).

### Qdrant (`sources/qdrant.py`)

**Credential fields:**
```python
def credential_fields(self) -> list[CredentialField]:
    return [
        CredentialField(key="host", label="Host URL", default="http://localhost:6333"),
        CredentialField(key="api_key", label="API Key (optional for Cloud)", is_secret=True, required=False),
    ]
```

**Connection:** `QdrantClient(url=..., api_key=...)`.

**List indexes:** `client.get_collections()` — return collection names.

**Inspect:** `client.get_collection(name)` — returns dimension (from config), vector count, distance metric. Qdrant has no namespace concept; `namespaces` is None.

**Extract:**
- Use `client.scroll(collection_name, limit=batch_size, offset=...)` for paginated extraction.
- Qdrant scroll returns `(records, next_offset)`. Yield `next_offset` as cursor.
- Each record has `.id`, `.vector`, `.payload` (metadata).
- `contents`: always None (Qdrant has no document/content concept).

### Weaviate (`sources/weaviate.py`)

**Credential fields:**
```python
def credential_fields(self) -> list[CredentialField]:
    return [
        CredentialField(key="host", label="Host URL", default="http://localhost:8080"),
        CredentialField(key="api_key", label="API Key (optional for Cloud)", is_secret=True, required=False),
    ]
```

**Connection:** `weaviate.connect_to_custom(...)` or `weaviate.connect_to_weaviate_cloud(...)`.

**List indexes:** List classes/collections via `client.collections.list_all()`.

**Inspect:** Get collection config for dimension, count via aggregation. Weaviate has no namespace concept; `namespaces` is None.

**Extract:**
- Use cursor-based iteration: `collection.iterator(include_vector=True)` which handles pagination internally.
- Each object has `.uuid` (use as ID), `.vector`, `.properties` (metadata).
- `contents`: always None (Weaviate has no separate document/content concept — text is stored in properties).

### ChromaDB (`sources/chromadb.py`)

**Credential fields:**
```python
def credential_fields(self) -> list[CredentialField]:
    return [
        CredentialField(key="mode", label="Mode", default="remote",
                        help_text="'local' for PersistentClient with a filesystem path, 'remote' for HttpClient"),
        CredentialField(key="path", label="Data Path", default="./chroma_data",
                        help_text="Filesystem path to ChromaDB data directory",
                        visible_when={"mode": "local"}),
        CredentialField(key="host", label="Host", default="localhost",
                        visible_when={"mode": "remote"}),
        CredentialField(key="port", label="Port", default="8000",
                        visible_when={"mode": "remote"}),
    ]
```

**Connection:** `chromadb.PersistentClient(path=...)` when mode is "local", or `chromadb.HttpClient(host=..., port=...)` when mode is "remote".

**List indexes:** `client.list_collections()`.

**Inspect:** `collection.count()` for vector count. Dimension requires fetching one sample vector. No explicit metric exposed by default (ChromaDB defaults to cosine). ChromaDB has no namespace concept; `namespaces` is None.

**Extract:**
- Use `collection.get(include=["embeddings", "metadatas", "documents"], offset=..., limit=batch_size)`.
- ChromaDB's `get()` supports offset/limit pagination. Yield `str(offset + len(batch))` as cursor.
- Map: `ids` → id, `embeddings` → vector, `metadatas` → metadata, `documents` → `contents`.
- `contents`: populated from ChromaDB's `documents` field (text stored alongside vectors).

### Milvus (`sources/milvus.py`)

**Credential fields:**
```python
def credential_fields(self) -> list[CredentialField]:
    return [
        CredentialField(key="uri", label="URI", default="http://localhost:19530"),
        CredentialField(key="token", label="Token (optional for Zilliz Cloud)", is_secret=True, required=False),
        CredentialField(key="database", label="Database", default="default"),
    ]
```

**Connection:** `connections.connect(uri=..., token=...)` or use `MilvusClient(uri=..., token=...)`.

**List indexes:** `utility.list_collections()` or `client.list_collections()`.

**Inspect:** `collection.describe()` for schema (dimension, fields), `collection.num_entities` for count. Extract metric from index params. If the collection has partitions, populate `namespaces` with partition names.

**Extract:**
- Use query iterator: `collection.query_iterator(expr="", output_fields=["*"], batch_size=batch_size)`.
- Alternatively, use `collection.query(expr="id >= {offset}", output_fields=[...], limit=batch_size)` with offset-based pagination.
- Milvus has a primary key field (could be int or string) — use as the vector ID.
- The vector field name is determined from the schema (field with `dtype=DataType.FLOAT_VECTOR`).
- If a namespace (partition) is selected, filter extraction to that partition.
- `contents`: if the schema contains a VARCHAR field that appears to be document content (heuristic: field name contains "content", "document", "text", or is the only VARCHAR field longer than 256 chars), map it to `contents`. Otherwise None.

---

## CyborgDB Destination Handler (`destination.py`)

The destination handler wraps CyborgDB operations:

```python
class CyborgDestination:
    def connect(self, host: str, api_key: str) -> None:
        """Connect and verify health."""

    def list_indexes(self) -> list[dict]:
        """List existing indexes with their metadata."""

    def create_index(
        self,
        name: str,
        dimension: int,
        index_type: str,        # "ivf", "ivfflat", "ivfpq"
        index_key: bytes,
        n_lists: int = 1024,    # Auto-calculated from vector count
    ) -> None:
        """Create a new encrypted index."""

    def load_index(self, name: str, index_key: bytes) -> None:
        """Load an existing index."""

    def upsert_batch(self, records: list[VectorRecord]) -> int:
        """
        Upsert a batch of records. Returns count of successfully upserted vectors.
        Maps VectorRecord to CyborgDB's upsert format:
          {"id": record.id, "vector": record.vector, "metadata": record.metadata}
        Also include "contents" if record.contents is not None.
        """

    def get_count(self) -> int:
        """Get total vector count in the loaded index."""

    def fetch_by_ids(self, ids: list[str]) -> list[VectorRecord]:
        """Fetch vectors by ID for spot-check verification."""
```

### Index Configuration Defaults

When auto-creating an index, derive `n_lists` from vector count:

| Vector Count | n_lists |
|-------------|---------|
| < 1,000 | 32 |
| 1,000 - 10,000 | 128 |
| 10,000 - 100,000 | 512 |
| 100,000 - 1,000,000 | 1,024 |
| > 1,000,000 | 4,096 |

For IVFPQ, also set `n_subquantizers` = dimension / 8 (clamped to a minimum of 8).

---

## Checkpoint System (`checkpoint.py`)

Checkpoint file: `./cyborgdb-migrate-checkpoints/{source_type}_{source_index}_{dest_index}.json`

```json
{
  "version": 1,
  "source_type": "pinecone",
  "source_index": "product-embeddings",
  "dest_index": "product-embeddings",
  "namespace": "default",
  "cursor": "eyJsYXN0X2lkIjogIml0ZW1fNTAwMCJ9",
  "vectors_migrated": 50000,
  "vectors_total": 98210,
  "started_at": "2025-02-10T14:00:00Z",
  "updated_at": "2025-02-10T14:30:22Z",
  "batch_size": 100,
  "batches_completed": 500
}
```

Checkpoint files include source type + source index + dest index in the filename, so stale checkpoints from different migrations are naturally ignored. Only a checkpoint matching the current source/dest combination is considered.

**On resume:**
1. Validate that source type, source index, and dest index match.
2. Pass `resume_from=cursor` to `source.extract()`.
3. Skip re-upserting already-migrated vectors (the cursor handles this on the source side; CyborgDB upsert is idempotent so duplicates are harmless).

---

## Migration Engine (`engine.py`)

The engine orchestrates the actual data movement. It is source-agnostic and UI-agnostic. It uses **double-buffering** to overlap source extraction with destination upsert for better throughput.

```python
class MigrationEngine:
    def __init__(
        self,
        source: SourceConnector,
        destination: CyborgDestination,
        source_info: SourceInfo,
        batch_size: int = 100,
        checkpoint_every: int = 10,
        spot_check_per_batch: int = 4,      # Number of random vectors to cache per batch for verification
        on_progress: Callable | None = None, # Callback for progress updates
        cancel_event: threading.Event | None = None,  # For graceful cancellation
    ):
        self._verification_samples: list[VectorRecord] = []  # Cached during extraction
        ...

    def run(
        self,
        namespace: str | None = None,
        resume: bool = False,
    ) -> MigrationResult:
        """
        Execute the migration with double-buffered extraction/upsert.

        Uses a producer-consumer pattern with a single-slot buffer:
        1. Extract batch N+1 from source (producer thread)
        2. Upsert batch N to destination (consumer/main thread)
        3. Overlap these operations for ~2x throughput on I/O-bound migrations.

        Flow:
        1. Call source.extract() with batch_size, namespace, and optional resume cursor.
        2. For each (batch, cursor) tuple yielded:
           a. Check cancel_event; if set, save checkpoint and return early.
           b. Cache spot_check_per_batch random vectors from this batch for later verification.
           c. Submit batch to destination via double-buffer (upsert previous batch while extracting next).
           d. Update progress counters.
           e. Every checkpoint_every batches, save checkpoint using the cursor from the tuple.
           f. Call on_progress callback if set.
        3. After all data is upserted, run verification using cached samples.
        4. Return MigrationResult.
        """

    def verify(self) -> tuple[bool, str]:
        """
        1. Compare total counts (source expected vs destination actual).
        2. Fetch cached sample vector IDs from CyborgDB.
        3. Compare vectors and metadata against the cached source copies.
        4. Return (passed: bool, details: str).

        Uses self._verification_samples which were cached during extraction,
        so the source does NOT need to be re-queried. This avoids issues with
        source timeouts or data changes after migration.
        """
```

**Double-buffering implementation:** Use a `queue.Queue(maxsize=1)` or `concurrent.futures.ThreadPoolExecutor(max_workers=1)`. The extraction iterator runs in the main worker thread, and each upsert is submitted to the executor. Before submitting the next upsert, wait for the previous one to complete. This gives simple, predictable overlap without complex async machinery.

**Verification via cached samples:** During extraction, the engine randomly selects `spot_check_per_batch` vectors from each batch and appends them to `_verification_samples`. There is no cap — every batch contributes samples. After migration completes, all cached source vectors are compared against the copies fetched from CyborgDB. The total count is also verified (source expected vs destination actual). This eliminates the need to re-query the source after migration, avoiding issues with connection timeouts or data drift.

**Retry logic**: Wrap `destination.upsert_batch()` in a retry decorator:
- Max 3 retries per batch.
- Exponential backoff: 1s, 2s, 4s.
- On final failure, log the batch (IDs + error) and continue.

**Cancellation**: The `cancel_event` is a `threading.Event` that the Textual MigrateScreen sets when the user clicks "Cancel Migration". The engine checks it between batches.

---

## CLI Entry Point (`cli.py`)

```python
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(
        prog="cyborgdb-migrate",
        description="Migrate vector data from other databases into CyborgDB",
    )
    parser.add_argument("--config", metavar="FILE", help="TOML config file for non-interactive mode")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint (non-interactive only)")
    parser.add_argument("--batch-size", type=int, default=100, help="Vectors per batch (default: 100)")
    parser.add_argument("--log-file", metavar="FILE", default="./cyborgdb-migrate.log",
                        help="Log file path (default: ./cyborgdb-migrate.log)")
    parser.add_argument("--quiet", action="store_true", help="Minimal output (non-interactive only)")
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")

    args = parser.parse_args()

    # Configure file logging
    setup_logging(args.log_file)

    if args.config:
        run_headless(args.config, args.batch_size, args.resume, args.log_file, args.quiet)
    else:
        if args.resume:
            print("Error: --resume is only supported with --config", file=sys.stderr)
            raise SystemExit(1)
        state = MigrationState()
        state.batch_size = args.batch_size
        app = MigrateApp(state)
        app.run()
```

**Logging:** All operations (batch upserts, retries, errors, checkpoints) are logged to `--log-file` (default: `./cyborgdb-migrate.log`). The TUI and headless mode both write to this file. This provides a persistent debugging trail for failed migrations.

---

## Testing Strategy

- **Unit tests for each source connector**: Mock the client libraries. Test `inspect()`, `extract()` pagination and `(batch, cursor)` tuple format, `credential_fields()`, and `configure()` validation.
- **Unit tests for engine**: Mock source and destination. Test batch flow, double-buffering, checkpoint save/load, retry logic, cancellation, sample caching, and verification.
- **Unit tests for config loader**: Test env var expansion, missing variable errors, and TOML parsing.
- **Textual pilot tests** (`test_app.py`): Use Textual's built-in `App.run_test()` (the "pilot" API) to simulate user interaction — pressing buttons, typing into inputs, navigating screens. Test the happy path (all 6 screens) and key error paths (connection failure, dimension mismatch).
- **Integration test** (optional, manual): Run against a local CyborgDB + ChromaDB instance with a small dataset. This is a smoke test, not CI.
- Use `pytest` as the test framework.

---

## Future Enhancements (Out of Scope for V1)

- **V1.5 — Explicit training support**: CyborgDB handles training automatically in V1. Add a post-migration screen that shows training progress, estimated time, and allows the user to wait or detach. Add `destination.train()` and `destination.is_trained()` methods.
- **Post-migration index browser**: A Textual screen to browse/query the newly created CyborgDB index. The framework is already in place to add screens.
- **Live migration dashboard**: A persistent Textual app that monitors ongoing migrations. Textual's reactive architecture makes this straightforward.
- `--from-file` mode: Import from an intermediate JSON/Parquet dump.
- **Metadata transformation rules**: Map/rename/filter metadata fields during migration.
- **Additional sources**: OpenSearch, Elasticsearch, pgvector, LanceDB, Faiss files.
- **Any-to-any migration**: Add a `DestinationConnector` interface mirroring `SourceConnector`. Refactor `CyborgDestination` to implement it. Add Pinecone, Qdrant, pgvector as destination connectors. Open-source as a vendor-neutral tool.
- **Dry run mode**: `--dry-run` to simulate the migration without writing to CyborgDB.
- **Multi-namespace batch migration**: A wrapper mode that runs the migration multiple times for each namespace in a source index, useful for scripted bulk migrations.
