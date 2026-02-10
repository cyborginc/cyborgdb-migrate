from textual.app import App

from cyborgdb_migrate.models import MigrationState
from cyborgdb_migrate.screens.source_select import SourceSelectScreen


class MigrateApp(App):
    """CyborgDB Migration Wizard TUI application."""

    CSS_PATH = "theme.css"
    TITLE = "CyborgDB Migration Wizard"

    def __init__(self, state: MigrationState | None = None) -> None:
        super().__init__()
        self.state = state or MigrationState()

    def on_mount(self) -> None:
        self.push_screen(SourceSelectScreen(self.state))
