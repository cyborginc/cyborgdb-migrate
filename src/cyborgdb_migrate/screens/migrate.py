from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from rich.text import Text
from textual import work
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Label, ProgressBar, RichLog, Static

from cyborgdb_migrate.checkpoint import load_checkpoint
from cyborgdb_migrate.engine import MigrationEngine, ProgressUpdate
from cyborgdb_migrate.widgets.step_header import StepHeader

if TYPE_CHECKING:
    from cyborgdb_migrate.models import MigrationResult, MigrationState


class MigrationProgress(Message):
    """Posted by worker to update UI."""

    def __init__(self, update: ProgressUpdate) -> None:
        super().__init__()
        self.update = update


class MigrationComplete(Message):
    """Posted when migration finishes."""

    def __init__(self, result: MigrationResult) -> None:
        super().__init__()
        self.result = result


class MigrationFailed(Message):
    """Posted on fatal error."""

    def __init__(self, error: str) -> None:
        super().__init__()
        self.error = error


class MigrateScreen(Screen):
    """Step 6: Live migration progress."""

    def __init__(self, state: MigrationState) -> None:
        super().__init__()
        self.state = state
        self._cancel_event = threading.Event()
        self._has_checkpoint = False

    def compose(self):
        src_name = ""
        dest_name = ""
        if self.state.source_info:
            src_name = self.state.source_info.index_or_collection_name
        if self.state.index_name:
            dest_name = self.state.index_name

        yield StepHeader(6, "Migrating")
        with Vertical(classes="step-content"):
            yield Label(f"{src_name} -> CyborgDB ({dest_name})")

            # Resume panel (hidden by default)
            with Vertical(id="resume-panel", classes="resume-panel"):
                yield Static("", id="resume-info")
                with Horizontal():
                    yield Button("Resume", id="resume-btn", variant="primary")
                    yield Button("Start Fresh", id="fresh-btn")

            # Progress area
            with Vertical(classes="progress-container"):
                yield ProgressBar(total=100, id="progress-bar")
                yield Label("Vectors:  0 / 0", id="vectors-label")
                yield Label("Batch:    0 / 0", id="batch-label")
                yield Label("Speed:    -- vec/s", id="speed-label")
                yield Label("Elapsed:  0s", id="elapsed-label")
                yield Label("Errors:   0", id="errors-label")

            yield RichLog(id="log", max_lines=500, wrap=True)

        with Horizontal(classes="button-row"):
            yield Button("Cancel Migration", id="cancel-btn", variant="error")

    def on_mount(self) -> None:
        self.state.ready_for_step(6)
        self.query_one("#resume-panel").display = False

        # Check for existing checkpoint
        info = self.state.source_info
        dest_name = self.state.index_name or ""
        cp = load_checkpoint(info.source_type, info.index_or_collection_name, dest_name)

        if cp is not None:
            self._has_checkpoint = True
            pct = (cp.vectors_migrated / cp.vectors_total * 100) if cp.vectors_total else 0
            self.query_one("#resume-panel").display = True
            self.query_one("#resume-info", Static).update(
                f"Found checkpoint: {cp.vectors_migrated:,} / {cp.vectors_total:,} "
                f"vectors ({pct:.0f}%)\n"
                f"Last updated: {cp.updated_at}"
            )
        else:
            self._start_migration(resume=False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self._cancel_event.set()
            log = self.query_one("#log", RichLog)
            log.write(Text.from_markup("[yellow]Cancelling migration...[/yellow]"))
        elif event.button.id == "resume-btn":
            self.query_one("#resume-panel").display = False
            self._start_migration(resume=True)
        elif event.button.id == "fresh-btn":
            self.query_one("#resume-panel").display = False
            self._start_migration(resume=False)

    @work(thread=True)
    async def _start_migration(self, resume: bool = False) -> None:
        try:
            engine = MigrationEngine(
                source=self.state.source_connector,
                destination=self.state.cyborgdb_destination,
                source_info=self.state.source_info,
                batch_size=self.state.batch_size,
                on_progress=self._on_progress,
                cancel_event=self._cancel_event,
            )

            result = engine.run(
                namespace=self.state.selected_namespace,
                resume=resume,
            )

            self.state.migration_result = result
            self.post_message(MigrationComplete(result))

        except Exception as e:
            self.post_message(MigrationFailed(str(e)))

    def _on_progress(self, update: ProgressUpdate) -> None:
        self.post_message(MigrationProgress(update))

    def on_migration_progress(self, event: MigrationProgress) -> None:
        u = event.update
        total = u.vectors_total or 1
        pct = u.vectors_migrated / total * 100

        self.query_one("#progress-bar", ProgressBar).update(progress=pct)
        self.query_one("#vectors-label", Label).update(
            f"Vectors:  {u.vectors_migrated:,} / {u.vectors_total:,}"
        )
        self.query_one("#batch-label", Label).update(
            f"Batch:    {u.batches_completed:,} / {u.batches_total:,}"
        )
        self.query_one("#speed-label", Label).update(
            f"Speed:    ~{u.speed_vectors_per_sec:,.0f} vec/s"
        )

        elapsed = u.elapsed_seconds
        mins, secs = divmod(int(elapsed), 60)
        self.query_one("#elapsed-label", Label).update(f"Elapsed:  {mins}m {secs}s")
        self.query_one("#errors-label", Label).update(f"Errors:   {u.errors}")

        if u.message:
            ts = time.strftime("%H:%M:%S")
            log = self.query_one("#log", RichLog)
            log.write(f"{ts}  {u.message}")

    def on_migration_complete(self, event: MigrationComplete) -> None:
        log = self.query_one("#log", RichLog)
        log.write(Text.from_markup("[green]Migration complete![/green]"))

        from cyborgdb_migrate.screens.summary import SummaryScreen

        self.app.push_screen(SummaryScreen(self.state))

    def on_migration_failed(self, event: MigrationFailed) -> None:
        log = self.query_one("#log", RichLog)
        log.write(Text.from_markup(f"[red]Fatal error: {event.error}[/red]"))
