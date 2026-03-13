from __future__ import annotations

import webbrowser
from typing import TYPE_CHECKING

from textual import work
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static

from cyborgdb_migrate.destination import CyborgDestination
from cyborgdb_migrate.widgets.step_header import StepHeader

if TYPE_CHECKING:
    from cyborgdb_migrate.models import MigrationState

_SIGNUP_URL = "https://cyborgdb.co/new"


class CyborgConnectScreen(Screen):
    """Step 4: Connect to CyborgDB."""

    def __init__(self, state: MigrationState) -> None:
        super().__init__()
        self.state = state

    def compose(self):
        yield StepHeader(4, "CyborgDB Connection")
        with Vertical(classes="step-content"):
            yield Label("CyborgDB Host URL:")
            yield Input(
                value="http://localhost:8000",
                placeholder="http://localhost:8000",
                id="host-input",
            )
            yield Label("CyborgDB API Key:")
            yield Input(password=True, id="api-key-input")
            yield Static(
                f"Need an API key? Get one free at [@click=screen.open_signup]{_SIGNUP_URL}[/]",
                id="api-key-hint",
            )
            yield Static("", id="error-label")
        with Horizontal(classes="button-row"):
            yield Button("Back", id="back-btn")
            yield Button("Connect & Continue", id="connect-btn", variant="primary")

    def on_mount(self) -> None:
        self.state.ready_for_step(4)

    def action_open_signup(self) -> None:
        webbrowser.open(_SIGNUP_URL)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()
        elif event.button.id == "connect-btn":
            self.query_one("#error-label", Static).update("")
            self._do_connect()

    @work(thread=True)
    async def _do_connect(self) -> None:
        connect_btn = self.query_one("#connect-btn", Button)
        self.app.call_from_thread(setattr, connect_btn, "label", "Connecting...")
        self.app.call_from_thread(setattr, connect_btn, "disabled", True)

        try:
            host = self.query_one("#host-input", Input).value.strip()
            api_key = self.query_one("#api-key-input", Input).value.strip()

            if not host:
                raise ValueError("Host URL is required")
            if not api_key:
                raise ValueError("API key is required")

            dest = CyborgDestination()
            dest.connect(host, api_key)

            # Validate credentials by listing indexes
            indexes = dest.list_indexes()

            self.state.cyborgdb_destination = dest
            self.state.existing_indexes = indexes

            self.app.call_from_thread(self._push_next)
        except Exception as e:
            msg = str(e)
            lower = msg.lower()
            if "401" in msg or "403" in msg or "unauthorized" in lower or "forbidden" in lower:
                msg = "Invalid API key. Please check your key and try again."
            self.app.call_from_thread(
                self.query_one("#error-label", Static).update,
                f"[red]{msg}[/red]",
            )
        finally:
            self.app.call_from_thread(setattr, connect_btn, "label", "Connect & Continue")
            self.app.call_from_thread(setattr, connect_btn, "disabled", False)

    def _push_next(self) -> None:
        from cyborgdb_migrate.screens.dest_index import DestIndexScreen

        self.app.push_screen(DestIndexScreen(self.state))
