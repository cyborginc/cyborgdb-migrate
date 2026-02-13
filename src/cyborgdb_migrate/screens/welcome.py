from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Static

from cyborgdb_migrate.widgets.logo import LOGO

if TYPE_CHECKING:
    from cyborgdb_migrate.models import MigrationState


class WelcomeScreen(Screen):
    """Welcome / landing screen with CyborgDB logo and Get Started button."""

    def __init__(self, state: MigrationState) -> None:
        super().__init__()
        self.state = state

    def compose(self):
        with Vertical(classes="welcome-content"):
            yield Static(LOGO, classes="welcome-logo")
            yield Static(
                "[bold]Migration Wizard[/]", classes="welcome-subtitle"
            )
            yield Static(
                "[dim]Migrate your vectors from any source database to CyborgDB.\n"
                "This wizard will guide you through the process step by step.[/]",
                classes="welcome-description",
            )
            with Center():
                yield Button("Get Started", id="get-started-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "get-started-btn":
            from cyborgdb_migrate.screens.source_select import SourceSelectScreen

            self.app.push_screen(SourceSelectScreen(self.state))
