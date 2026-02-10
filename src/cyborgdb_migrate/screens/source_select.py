from __future__ import annotations

from typing import TYPE_CHECKING

from textual import work
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, LoadingIndicator, OptionList, Static
from textual.widgets.option_list import Option

from cyborgdb_migrate.sources import SOURCE_REGISTRY
from cyborgdb_migrate.widgets.source_form import SourceForm
from cyborgdb_migrate.widgets.step_header import StepHeader

if TYPE_CHECKING:
    from cyborgdb_migrate.models import MigrationState


class SourceSelectScreen(Screen):
    """Step 1: Select source database and enter credentials."""

    def __init__(self, state: MigrationState) -> None:
        super().__init__()
        self.state = state
        self._source_names = list(SOURCE_REGISTRY.keys())
        self._current_source = None

    def compose(self):
        yield StepHeader(1, "Select Source")
        with Vertical(classes="step-content"):
            yield Label("Where are you migrating from?")
            yield OptionList(
                *[Option(name, id=name) for name in self._source_names],
                id="source-list",
            )
            yield Label("")
            yield SourceForm(id="source-form")
            yield Static("", id="error-label")
            yield LoadingIndicator(id="connect-loading")
        with Horizontal(classes="button-row"):
            yield Button("Connect & Continue", id="connect-btn", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#connect-loading", LoadingIndicator).display = False
        # The OptionList will fire OptionHighlighted for the first item automatically

    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id == "source-list" and event.option:
            await self._select_source(str(event.option.prompt))

    async def _select_source(self, name: str) -> None:
        if self._current_source is not None and self._current_source.name() == name:
            return
        source_cls = SOURCE_REGISTRY.get(name)
        if source_cls is None:
            return
        self._current_source = source_cls()
        form = self.query_one("#source-form", SourceForm)
        await form.rebuild(self._current_source.credential_fields())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "connect-btn":
            self._do_connect()

    @work(thread=True)
    async def _do_connect(self) -> None:
        error_label = self.query_one("#error-label", Static)
        loading = self.query_one("#connect-loading", LoadingIndicator)

        self.app.call_from_thread(setattr, error_label, "update", "")
        self.app.call_from_thread(setattr, loading, "display", True)

        try:
            form = self.query_one("#source-form", SourceForm)
            credentials = form.get_values()
            self._current_source.configure(credentials)
            self._current_source.connect()

            self.state.source_connector = self._current_source
            self.app.call_from_thread(self._push_next)
        except Exception as e:
            self.app.call_from_thread(error_label.update, f"[red]Error: {e}[/red]")
        finally:
            self.app.call_from_thread(setattr, loading, "display", False)

    def _push_next(self) -> None:
        from cyborgdb_migrate.screens.source_inspect import SourceInspectScreen

        self.app.push_screen(SourceInspectScreen(self.state))
