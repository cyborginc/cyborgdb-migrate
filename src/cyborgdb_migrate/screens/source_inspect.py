from __future__ import annotations

from typing import TYPE_CHECKING

from textual import work
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, LoadingIndicator, OptionList, Static
from textual.widgets.option_list import Option

from cyborgdb_migrate.widgets.step_header import StepHeader

if TYPE_CHECKING:
    from cyborgdb_migrate.models import MigrationState, SourceInfo


class SourceInspectScreen(Screen):
    """Step 3: Select index and namespace, view summary."""

    def __init__(self, state: MigrationState) -> None:
        super().__init__()
        self.state = state
        self._indexes: list[str] = []
        self._source_info: SourceInfo | None = None

    def compose(self):
        yield StepHeader(3, "Select Data")
        with Vertical(classes="step-content"):
            yield Label("Select an index to migrate:")
            yield LoadingIndicator(id="index-loading")
            yield OptionList(id="index-list")
            yield Label("Select a namespace:", id="ns-label")
            yield OptionList(id="ns-list")
            yield Static("", id="summary-panel", classes="summary-panel")
        with Horizontal(classes="button-row"):
            yield Button("Back", id="back-btn")
            yield Button("Continue", id="continue-btn", variant="primary", disabled=True)

    def on_mount(self) -> None:
        self.state.ready_for_step(3)
        self.query_one("#ns-label").display = False
        self.query_one("#ns-list").display = False
        self.query_one("#summary-panel").display = False
        self._load_indexes()

    @work(thread=True)
    async def _load_indexes(self) -> None:
        loading = self.query_one("#index-loading", LoadingIndicator)
        try:
            indexes = self.state.source_connector.list_indexes()
            self._indexes = indexes

            def update_list():
                loading.display = False
                if not indexes:
                    self.query_one("#index-list", OptionList).display = False
                    self.query_one("#summary-panel", Static).display = True
                    self.query_one("#summary-panel", Static).update(
                        "[red]No indexes found. Please ensure your database contains data.[/red]"
                    )
                    return
                idx_list = self.query_one("#index-list", OptionList)
                idx_list.clear_options()
                for name in indexes:
                    idx_list.add_option(Option(name, id=name))

            self.app.call_from_thread(update_list)
        except Exception as e:
            self.app.call_from_thread(loading.update, f"Error: {e}")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle click/enter on an option (works even if already highlighted)."""
        if event.option_list.id == "index-list" and event.option:
            self._inspect_index(str(event.option.prompt))

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id == "index-list" and event.option:
            self._inspect_index(str(event.option.prompt))
        elif event.option_list.id == "ns-list" and event.option:
            ns = str(event.option.prompt)
            self.state.selected_namespace = ns
            self._update_summary()

    @work(thread=True)
    async def _inspect_index(self, index_name: str) -> None:
        try:
            info = self.state.source_connector.inspect(index_name)
            self._source_info = info
            self.state.source_info = info

            def update_ui():
                # Show namespace list if applicable
                if info.namespaces and len(info.namespaces) > 1:
                    ns_label = self.query_one("#ns-label")
                    ns_list = self.query_one("#ns-list", OptionList)
                    ns_label.display = True
                    ns_list.display = True
                    ns_list.clear_options()
                    for ns in info.namespaces:
                        ns_list.add_option(Option(ns, id=ns))
                else:
                    self.query_one("#ns-label").display = False
                    self.query_one("#ns-list").display = False
                    self.state.selected_namespace = None

                self._update_summary()
                self.query_one("#continue-btn", Button).disabled = False

            self.app.call_from_thread(update_ui)
        except Exception as e:
            def show_error():
                panel = self.query_one("#summary-panel", Static)
                panel.display = True
                panel.update(f"[red]Error inspecting index: {e}[/red]")

            self.app.call_from_thread(show_error)

    def _update_summary(self) -> None:
        info = self._source_info
        if info is None:
            return
        panel = self.query_one("#summary-panel", Static)
        panel.display = True
        lines = [
            f"  Source:     {info.source_type.title()}",
            f"  Index:      {info.index_or_collection_name}",
        ]
        if self.state.selected_namespace:
            lines.append(f"  Namespace:  {self.state.selected_namespace}")
        lines.extend([
            f"  Dimension:  {info.dimension}",
            f"  Vectors:    {info.vector_count:,}",
        ])
        if info.metadata_fields:
            lines.append(f"  Metadata:   {', '.join(info.metadata_fields[:10])}")
        if info.metric:
            lines.append(f"  Metric:     {info.metric}")
        panel.update("\n".join(lines))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()
        elif event.button.id == "continue-btn":
            from cyborgdb_migrate.screens.cyborgdb_connect import CyborgConnectScreen

            self.app.push_screen(CyborgConnectScreen(self.state))
