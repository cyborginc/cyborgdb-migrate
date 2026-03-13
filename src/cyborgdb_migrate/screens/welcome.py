from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Center, Vertical
from textual.events import Resize
from textual.screen import Screen
from textual.widgets import Button, Static

from cyborgdb_migrate.widgets.logo import LOGO

MIN_WIDTH = 120
MIN_HEIGHT = 50

if TYPE_CHECKING:
    from cyborgdb_migrate.models import MigrationState


class WelcomeScreen(Screen):
    """Welcome / landing screen with CyborgDB logo and Get Started button."""

    def __init__(self, state: MigrationState) -> None:
        super().__init__()
        self.state = state

    def compose(self):
        yield Static("", id="size-msg", classes="size-warning")
        with Vertical(classes="welcome-content", id="welcome-main"):
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

    def on_mount(self) -> None:
        self._check_size()

    def on_resize(self, event: Resize) -> None:
        self._check_size()

    def _check_size(self) -> None:
        w, h = self.size.width, self.size.height
        too_narrow = w < MIN_WIDTH
        too_short = h < MIN_HEIGHT

        warning = self.query_one("#size-msg", Static)
        main = self.query_one("#welcome-main")

        if too_narrow or too_short:
            if too_narrow and too_short:
                msg = (
                    f"Terminal too small ({w}x{h}).\n"
                    f"Please resize to at least {MIN_WIDTH}x{MIN_HEIGHT}."
                )
            elif too_narrow:
                msg = (
                    f"Terminal too narrow ({w} columns).\n"
                    f"Please widen to at least {MIN_WIDTH} columns."
                )
            else:
                msg = (
                    f"Terminal too short ({h} rows).\n"
                    f"Please increase height to at least {MIN_HEIGHT} rows."
                )
            warning.update(msg)
            warning.display = True
            main.display = False
        else:
            warning.display = False
            main.display = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "get-started-btn":
            from cyborgdb_migrate.screens.source_select import SourceSelectScreen

            self.app.push_screen(SourceSelectScreen(self.state))
