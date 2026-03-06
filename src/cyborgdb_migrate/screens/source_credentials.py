from __future__ import annotations

from typing import TYPE_CHECKING

from textual import work
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Static

from cyborgdb_migrate.widgets.source_form import SourceForm
from cyborgdb_migrate.widgets.step_header import StepHeader

if TYPE_CHECKING:
    from cyborgdb_migrate.models import MigrationState


class SourceCredentialsScreen(Screen):
    """Step 2: Enter credentials for the selected source and connect."""

    def __init__(self, state: MigrationState) -> None:
        super().__init__()
        self.state = state

    def compose(self):
        yield StepHeader(2, "Credentials")
        with Vertical(classes="step-content"):
            yield SourceForm(id="source-form")
            yield Static("", id="error-label")
        with Horizontal(classes="button-row"):
            yield Button("Back", id="back-btn")
            yield Button("Connect & Continue", id="connect-btn", variant="primary")

    async def on_mount(self) -> None:
        self.state.ready_for_step(2)
        form = self.query_one("#source-form", SourceForm)
        await form.rebuild(self.state.source_connector.credential_fields())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()
        elif event.button.id == "connect-btn":
            self._do_connect()

    @work(thread=True)
    async def _do_connect(self) -> None:
        error_label = self.query_one("#error-label", Static)
        connect_btn = self.query_one("#connect-btn", Button)

        self.app.call_from_thread(error_label.update, "")
        self.app.call_from_thread(setattr, connect_btn, "label", "Connecting...")
        self.app.call_from_thread(setattr, connect_btn, "disabled", True)

        try:
            form = self.query_one("#source-form", SourceForm)
            credentials = form.get_values()
            self.state.source_connector.configure(credentials)
            self.state.source_connector.connect()

            self.app.call_from_thread(self._push_next)
        except Exception as e:
            self.app.call_from_thread(error_label.update, f"[red]Error: {e}[/red]")
        finally:
            self.app.call_from_thread(setattr, connect_btn, "label", "Connect & Continue")
            self.app.call_from_thread(setattr, connect_btn, "disabled", False)

    def _push_next(self) -> None:
        from cyborgdb_migrate.screens.source_inspect import SourceInspectScreen

        self.app.push_screen(SourceInspectScreen(self.state))
