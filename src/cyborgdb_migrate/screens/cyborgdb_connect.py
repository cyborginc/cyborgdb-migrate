from __future__ import annotations

from typing import TYPE_CHECKING

from textual import work
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, LoadingIndicator, Static

from cyborgdb_migrate.destination import CyborgDestination
from cyborgdb_migrate.widgets.step_header import StepHeader

if TYPE_CHECKING:
    from cyborgdb_migrate.models import MigrationState


class CyborgConnectScreen(Screen):
    """Step 4: Connect to CyborgDB."""

    def __init__(self, state: MigrationState) -> None:
        super().__init__()
        self.state = state

    def compose(self):
        yield StepHeader(4, "CyborgDB Connection")
        with Vertical(classes="step-content"):
            yield Label("CyborgDB host URL:")
            yield Input(
                value="http://localhost:8000",
                placeholder="http://localhost:8000",
                id="host-input",
            )
            yield Label("CyborgDB API key:")
            yield Input(password=True, id="api-key-input")
            yield Static("", id="error-label")
            yield LoadingIndicator(id="connect-loading")
        with Horizontal(classes="button-row"):
            yield Button("Back", id="back-btn")
            yield Button("Connect & Continue", id="connect-btn", variant="primary")

    def on_mount(self) -> None:
        self.state.ready_for_step(4)
        self.query_one("#connect-loading", LoadingIndicator).display = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()
        elif event.button.id == "connect-btn":
            self._do_connect()

    @work(thread=True)
    async def _do_connect(self) -> None:
        error_label = self.query_one("#error-label", Static)
        loading = self.query_one("#connect-loading", LoadingIndicator)

        self.app.call_from_thread(error_label.update, "")
        self.app.call_from_thread(setattr, loading, "display", True)

        try:
            host = self.query_one("#host-input", Input).value.strip()
            api_key = self.query_one("#api-key-input", Input).value.strip()

            if not host:
                raise ValueError("Host URL is required")
            if not api_key:
                raise ValueError("API key is required")

            dest = CyborgDestination()
            dest.connect(host, api_key)
            self.state.cyborgdb_destination = dest

            self.app.call_from_thread(self._push_next)
        except Exception as e:
            self.app.call_from_thread(error_label.update, f"[red]Error: {e}[/red]")
        finally:
            self.app.call_from_thread(setattr, loading, "display", False)

    def _push_next(self) -> None:
        from cyborgdb_migrate.screens.dest_index import DestIndexScreen

        self.app.push_screen(DestIndexScreen(self.state))
