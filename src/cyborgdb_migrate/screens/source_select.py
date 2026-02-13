from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, OptionList
from textual.widgets.option_list import Option

from cyborgdb_migrate.sources import SOURCE_REGISTRY
from cyborgdb_migrate.widgets.step_header import StepHeader

if TYPE_CHECKING:
    from cyborgdb_migrate.models import MigrationState


class SourceSelectScreen(Screen):
    """Step 1: Select source database."""

    def __init__(self, state: MigrationState) -> None:
        super().__init__()
        self.state = state
        self._source_names = list(SOURCE_REGISTRY.keys())

    def compose(self):
        yield StepHeader(1, "Select Source")
        with Vertical(classes="step-content"):
            yield Label("Where are you migrating from?")
            yield OptionList(
                *[Option(name, id=name) for name in self._source_names],
                id="source-list",
            )
        with Horizontal(classes="button-row"):
            yield Button("Continue", id="continue-btn", variant="primary")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._do_continue()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "continue-btn":
            self._do_continue()

    def _do_continue(self) -> None:
        option_list = self.query_one("#source-list", OptionList)
        if option_list.highlighted is None:
            return
        name = str(option_list.get_option_at_index(option_list.highlighted).prompt)
        source_cls = SOURCE_REGISTRY.get(name)
        if source_cls is None:
            return
        self.state.source_connector = source_cls()

        from cyborgdb_migrate.screens.source_credentials import SourceCredentialsScreen

        self.app.push_screen(SourceCredentialsScreen(self.state))
