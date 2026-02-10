from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Static

from cyborgdb_migrate.widgets.step_header import StepHeader

if TYPE_CHECKING:
    from cyborgdb_migrate.models import MigrationState


class SummaryScreen(Screen):
    """Step 6: Verification results and quickstart snippet."""

    def __init__(self, state: MigrationState) -> None:
        super().__init__()
        self.state = state

    def compose(self):
        yield StepHeader(6, "Complete")
        with Vertical(classes="step-content"):
            yield Static("", id="verification-results")
            yield Static("", id="migration-summary", classes="summary-panel")
            yield Static("", id="quickstart-code", classes="summary-panel")
        with Horizontal(classes="button-row"):
            yield Button("Done", id="done-btn", variant="primary")

    def on_mount(self) -> None:
        result = self.state.migration_result
        if result is None:
            return

        # Verification results
        count_ok = result.vectors_migrated >= result.vectors_expected
        count_icon = "[green]OK[/green]" if count_ok else "[red]FAIL[/red]"
        spot_icon = "[green]OK[/green]" if result.spot_check_passed else "[red]FAIL[/red]"

        verif = (
            f"  {count_icon} Count check: "
            f"{result.vectors_migrated:,} / {result.vectors_expected:,} vectors\n"
            f"  {spot_icon} Spot check: {result.spot_check_details}"
        )
        self.query_one("#verification-results", Static).update(verif)

        # Migration summary
        mins, secs = divmod(int(result.duration_seconds), 60)
        source_name = ""
        source_index = ""
        if self.state.source_info:
            source_name = self.state.source_info.source_type.title()
            source_index = self.state.source_info.index_or_collection_name

        summary_lines = [
            f"  Source:    {source_name} / {source_index}",
            f"  Dest:     CyborgDB / {result.index_name}",
            f"  Vectors:  {result.vectors_migrated:,}",
            f"  Duration: {mins}m {secs}s",
        ]
        if result.key_file_path:
            summary_lines.append(f"  Key file: {result.key_file_path}")
        self.query_one("#migration-summary", Static).update("\n".join(summary_lines))

        # Quickstart code
        code = (
            'from cyborgdb import Client\n'
            '\n'
            'client = Client(\n'
            '    "https://localhost:8000", api_key\n'
            ')\n'
            'index = client.load_index(\n'
            f'    "{result.index_name}", index_key\n'
            ')\n'
            'results = index.query(\n'
            '    query_vectors=[...], top_k=10\n'
            ')\n'
        )
        from rich.syntax import Syntax

        syntax = Syntax(code, "python", theme="monokai", line_numbers=False)
        self.query_one("#quickstart-code", Static).update(syntax)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "done-btn":
            self.app.exit(0)
