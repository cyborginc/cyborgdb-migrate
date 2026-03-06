from __future__ import annotations

import base64
from typing import TYPE_CHECKING

from textual import work
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    Input,
    Label,
    OptionList,
    RadioButton,
    RadioSet,
    Static,
)
from textual.widgets.option_list import Option

from cyborgdb_migrate.destination import compute_n_lists
from cyborgdb_migrate.widgets.key_warning import KeyWarningModal
from cyborgdb_migrate.widgets.step_header import StepHeader

if TYPE_CHECKING:
    from cyborgdb_migrate.models import MigrationState


class DestIndexScreen(Screen):
    """Step 5: Create or select destination index + encryption key."""

    def __init__(self, state: MigrationState) -> None:
        super().__init__()
        self.state = state
        self._mode = "create"  # "create" or "existing"

        # Pre-compute index type labels based on vector count
        count = self.state.source_info.vector_count if self.state.source_info else 0
        if count < 10_000:
            self._ivfflat_label = "IVFFlat (recommended for small datasets)"
            self._ivfpq_label = "IVFPQ"
        elif count <= 500_000:
            self._ivfflat_label = f"IVFFlat (recommended for ~{count:,} vectors)"
            self._ivfpq_label = "IVFPQ"
        else:
            self._ivfflat_label = "IVFFlat"
            self._ivfpq_label = "IVFPQ (recommended for large datasets)"

    def compose(self):
        yield StepHeader(5, "Destination Index")
        with Vertical(classes="step-content"):
            yield OptionList(
                Option("Create new index", id="create"),
                Option("Use existing index", id="existing"),
                id="mode-list",
            )

            # Create new index form
            with Vertical(id="create-form"):
                yield Label("Index name:")
                default_name = ""
                if self.state.source_info:
                    default_name = self.state.source_info.index_or_collection_name
                yield Input(value=default_name, id="index-name-input")

                yield Label("Index type:")
                yield RadioSet(
                    RadioButton(self._ivfflat_label, value=True, id="type-ivfflat"),
                    RadioButton(self._ivfpq_label, id="type-ivfpq"),
                    id="index-type-radio",
                )

                yield Static("", id="config-summary")

                yield Label("Encryption key:")
                yield RadioSet(
                    RadioButton("Generate a new key (recommended)", value=True, id="gen-key"),
                    RadioButton("Provide my own key", id="own-key"),
                    id="key-radio",
                )
                yield Input(
                    placeholder="Base64-encoded 32-byte key",
                    password=True,
                    id="own-key-input",
                )

            # Existing index form
            with Vertical(id="existing-form"):
                yield Label("Select an existing index:")
                yield OptionList(id="existing-list")
                yield Label("Encryption key:")
                yield Input(
                    placeholder="Base64-encoded 32-byte key",
                    password=True,
                    id="existing-key-input",
                )

            yield Static("", id="error-label")

        with Horizontal(classes="button-row"):
            yield Button("Back", id="back-btn")
            yield Button("Continue", id="continue-btn", variant="primary")

    def on_mount(self) -> None:
        self.state.ready_for_step(5)
        self.query_one("#existing-form").display = False
        self.query_one("#own-key-input").display = False
        self._update_config_summary()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id == "mode-list" and event.option:
            mode = event.option.id
            self._mode = mode
            self.query_one("#create-form").display = mode == "create"
            self.query_one("#existing-form").display = mode == "existing"
            if mode == "existing":
                self._load_existing_indexes()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.radio_set.id == "index-type-radio":
            self._update_config_summary()
        elif event.radio_set.id == "key-radio":
            pressed = event.pressed
            self.query_one("#own-key-input").display = pressed.id == "own-key"

    def _load_existing_indexes(self) -> None:
        indexes = self.state.existing_indexes
        lst = self.query_one("#existing-list", OptionList)
        lst.clear_options()
        if not indexes:
            self.query_one("#error-label", Static).update(
                "[yellow]No existing indexes found. Go back and create a new index instead.[/yellow]"
            )
        else:
            for name in indexes:
                lst.add_option(Option(name, id=name))

    def _update_config_summary(self) -> None:
        dim = self.state.source_info.dimension if self.state.source_info else 0
        count = self.state.source_info.vector_count if self.state.source_info else 0
        n_lists = compute_n_lists(count)

        # Determine selected type
        idx_type = self._get_selected_index_type()
        summary = f"Index config: {idx_type.upper()}, dimension={dim}, n_lists={n_lists}"
        if idx_type == "ivfpq":
            pq_dim = max(8, dim // 8)
            summary += f", pq_dim={pq_dim}, pq_bits=8"

        self.query_one("#config-summary", Static).update(summary)

    def _get_selected_index_type(self) -> str:
        radio = self.query_one("#index-type-radio", RadioSet)
        if radio.pressed_button:
            btn_id = radio.pressed_button.id or ""
            if "ivfpq" in btn_id:
                return "ivfpq"
            if "ivf" in btn_id and "flat" not in btn_id:
                return "ivf"
        return "ivfflat"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()
        elif event.button.id == "continue-btn":
            self._do_continue()

    @work(thread=True)
    async def _do_continue(self) -> None:
        error_label = self.query_one("#error-label", Static)
        self.app.call_from_thread(error_label.update, "")

        try:
            if self._mode == "create":
                self._handle_create()
            else:
                self._handle_existing()
        except Exception as e:
            self.app.call_from_thread(error_label.update, f"[red]Error: {e}[/red]")

    def _handle_create(self) -> None:
        index_name = self.query_one("#index-name-input", Input).value.strip()
        if not index_name:
            raise ValueError("Index name is required")

        idx_type = self._get_selected_index_type()
        dim = self.state.source_info.dimension
        count = self.state.source_info.vector_count
        n_lists = compute_n_lists(count)
        metric = self.state.source_info.metric

        # Determine key
        key_radio = self.query_one("#key-radio", RadioSet)
        generate_key = True
        if key_radio.pressed_button and key_radio.pressed_button.id == "own-key":
            generate_key = False

        dest = self.state.cyborgdb_destination

        if index_name in self.state.existing_indexes:
            raise ValueError(
                f"Index '{index_name}' already exists. "
                "Choose a different name or use an existing index."
            )

        if generate_key:
            key_bytes, key_path = dest.generate_and_save_key(index_name=index_name)
            self.state.index_key = key_bytes
            self.state.key_file_path = key_path

            # Show key warning modal
            def show_modal():
                self.app.push_screen(
                    KeyWarningModal(key_path),
                    callback=lambda confirmed: self._on_key_confirmed(
                        confirmed, index_name, dim, idx_type, key_bytes, n_lists, metric
                    ),
                )

            self.app.call_from_thread(show_modal)
        else:
            key_b64 = self.query_one("#own-key-input", Input).value.strip()
            if not key_b64:
                raise ValueError("Encryption key is required")
            key_bytes = base64.b64decode(key_b64)
            if len(key_bytes) != 32:
                raise ValueError("Key must be exactly 32 bytes")
            self.state.index_key = key_bytes

            dest.create_index(
                name=index_name,
                dimension=dim,
                index_type=idx_type,
                index_key=key_bytes,
                n_lists=n_lists,
                metric=metric,
            )
            self.state.index_name = index_name
            self.app.call_from_thread(self._push_next)

    def _on_key_confirmed(
        self, confirmed: bool, index_name: str, dim: int,
        idx_type: str, key_bytes: bytes, n_lists: int, metric: str | None
    ) -> None:
        if not confirmed:
            return

        try:
            self.state.cyborgdb_destination.create_index(
                name=index_name,
                dimension=dim,
                index_type=idx_type,
                index_key=key_bytes,
                n_lists=n_lists,
                metric=metric,
            )
            self.state.index_name = index_name
            self._push_next()
        except Exception as e:
            self.query_one("#error-label", Static).update(f"[red]Error: {e}[/red]")

    def _handle_existing(self) -> None:
        existing_list = self.query_one("#existing-list", OptionList)
        if existing_list.highlighted is None:
            raise ValueError("Select an existing index")

        index_name = str(existing_list.get_option_at_index(existing_list.highlighted).prompt)
        key_b64 = self.query_one("#existing-key-input", Input).value.strip()
        if not key_b64:
            raise ValueError("Encryption key is required")

        key_bytes = base64.b64decode(key_b64)
        dest = self.state.cyborgdb_destination
        dest.load_index(index_name, key_bytes)

        # Validate dimension match
        source_dim = self.state.source_info.dimension
        dest_dim = dest.get_index_dimension()
        if dest_dim is not None and dest_dim != source_dim:
            raise ValueError(
                f"Dimension mismatch: source has {source_dim}d, destination has {dest_dim}d"
            )

        # Warn if index already has vectors
        try:
            existing_count = dest.get_count()
            if existing_count > 0:
                self.app.call_from_thread(
                    self.notify,
                    f"This index contains {existing_count:,} vectors. "
                    "Existing IDs will be overwritten on upsert.",
                    severity="warning",
                )
        except Exception:
            pass

        self.state.index_name = index_name
        self.state.index_key = key_bytes
        self.app.call_from_thread(self._push_next)

    def _push_next(self) -> None:
        from cyborgdb_migrate.screens.migrate import MigrateScreen

        self.app.push_screen(MigrateScreen(self.state))
