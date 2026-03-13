import time

from textual.app import App
from textual.theme import Theme

from cyborgdb_migrate.models import MigrationState
from cyborgdb_migrate.screens.welcome import WelcomeScreen

MIN_WIDTH = 80
MIN_HEIGHT = 24

CYBORGDB_THEME = Theme(
    name="cyborgdb",
    primary="#217684",
    secondary="#56D3DB",
    accent="#38C3EE",
    surface="#1a2a2e",
    background="#111d20",
    panel="#1e3438",
    warning="#f5a623",
    error="#e74c3c",
    success="#2ecc71",
    dark=True,
)


class MigrateApp(App):
    """CyborgDB Migration Wizard TUI application."""

    CSS_PATH = "theme.css"
    TITLE = "CyborgDB Migration Wizard"

    BINDINGS = [
        ("ctrl+q", "", ""),  # unbind default quit
    ]

    _ctrl_c_time: float = 0.0

    def __init__(self, state: MigrationState | None = None) -> None:
        super().__init__()
        self.state = state or MigrationState()

    def action_quit(self) -> None:
        """Disable the default quit action."""

    def _on_key(self, event) -> None:
        if event.key == "ctrl+c":
            now = time.monotonic()
            if now - self._ctrl_c_time < 1.0:
                self.exit()
            else:
                self._ctrl_c_time = now
                self.notify("Press Ctrl+C again to quit", timeout=1)

    def on_mount(self) -> None:
        self.register_theme(CYBORGDB_THEME)
        self.theme = "cyborgdb"
        self.push_screen(WelcomeScreen(self.state))
