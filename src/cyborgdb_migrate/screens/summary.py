from __future__ import annotations

import io
import re
import sys
from typing import TYPE_CHECKING

from textual import work
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, RichLog, Static, TextArea

from cyborgdb_migrate.widgets.step_header import StepHeader

if TYPE_CHECKING:
    from cyborgdb_migrate.models import MigrationState

_DEFAULT_SNIPPET = """\
import base64
from cyborgdb import Client

# Connect to CyborgDB
client = Client("{base_url}", "{api_key}")

# Load index with encryption key
with open("{key_file}") as f:
    index_key = base64.b64decode(f.read())
index = client.load_index("{index_name}", index_key)

# List some IDs
ids = index.list_ids()[:2]
print(f"Sample IDs: {{ids}}")

# Fetch a vector
item = index.get(ids=ids[:1], include=["vector", "metadata"])[0]
print(f"\\n  {{item['id']}}: dim={{len(item.get('vector', []))}}")
print(f"  metadata={{item.get('metadata')}}")

# Query nearest neighbors
vec = item.get("vector")
if vec:
    hits = index.query(query_vectors=vec, top_k=5)
    print(f"\\nNearest neighbors:")
    for h in hits:
        print(f"  {{h['id']}}  distance={{h.get('distance', '?')}}")
else:
    print("\\nNo vector returned — try include=['vector']")
"""


class SummaryScreen(Screen):
    """Step 7: Verification results and quickstart snippet."""

    def __init__(self, state: MigrationState) -> None:
        super().__init__()
        self.state = state

    def compose(self):
        yield StepHeader(7, "Complete")
        with Vertical(classes="step-content"):
            yield Static("", id="migration-summary", classes="summary-panel")
            yield Static("Migration complete! Try CyborgDB below:")
            yield TextArea(
                _DEFAULT_SNIPPET,
                language="python",
                theme="monokai",
                tab_behavior="indent",
                id="code-editor",
            )
            with Horizontal(id="run-row"):
                yield Button("Copy", id="copy-btn")
                yield Button("Run", id="run-btn", variant="success")
            yield RichLog(id="run-output", wrap=True, markup=True)
        with Horizontal(classes="button-row"):
            yield Button("Done", id="done-btn", variant="primary")

    def on_mount(self) -> None:
        result = self.state.migration_result
        if result is None:
            return

        mins, secs = divmod(int(result.duration_seconds), 60)
        source_name = ""
        source_index = ""
        if self.state.source_info:
            source_name = self.state.source_info.source_type.title()
            source_index = self.state.source_info.index_or_collection_name

        count_ok = result.vectors_migrated >= result.vectors_expected
        count_color = "green" if count_ok else "red"
        spot_color = "green" if result.spot_check_passed else "red"

        # Extract "N/M verified" from spot_check_details
        spot_match = re.search(r"(\d+)/(\d+) verified", result.spot_check_details)
        spot_text = (
            f"Checked: {spot_match.group(1)}/{spot_match.group(2)}"
            if spot_match
            else result.spot_check_details
        )

        summary_lines = [
            f"  Source:    {source_name} / {source_index}",
            f"  Dest:     CyborgDB / {result.index_name}",
            f"  Vectors:  [{count_color}]{result.vectors_migrated:,}"
            f" / {result.vectors_expected:,}[/{count_color}]",
            f"  Spot:     [{spot_color}]{spot_text}[/{spot_color}]",
            f"  Duration: {mins}m {secs}s",
        ]
        if result.key_file_path:
            summary_lines.append(f"  Key file: {result.key_file_path}")
        self.query_one("#migration-summary", Static).update(
            "\n".join(summary_lines)
        )

        # Fill in actual connection details in the snippet
        dest = self.state.cyborgdb_destination
        base_url = (
            getattr(dest, "_host", "http://localhost:8000")
            if dest
            else "http://localhost:8000"
        )
        api_key = getattr(dest, "_api_key", "YOUR_API_KEY")
        key_file = result.key_file_path or "path/to/key.key"

        snippet = _DEFAULT_SNIPPET.format(
            base_url=base_url,
            api_key=api_key or "YOUR_API_KEY",
            key_file=key_file,
            index_name=result.index_name,
        )
        editor = self.query_one("#code-editor", TextArea)
        editor.load_text(snippet)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "done-btn":
            self.app.exit(0)
        elif event.button.id == "run-btn":
            self._run_code()
        elif event.button.id == "copy-btn":
            self._copy_code()

    def _copy_code(self) -> None:
        import subprocess

        code = self.query_one("#code-editor", TextArea).text
        try:
            subprocess.run(
                ["pbcopy"], input=code.encode(), check=True,
            )
            self.notify("Copied to clipboard")
        except Exception:
            self.notify("Copy failed", severity="error")

    @work(thread=True)
    def _run_code(self) -> None:
        run_btn = self.query_one("#run-btn", Button)
        log = self.query_one("#run-output", RichLog)

        self.app.call_from_thread(setattr, run_btn, "disabled", True)
        self.app.call_from_thread(log.clear)

        code = self.query_one("#code-editor", TextArea).text
        namespace: dict = {}

        # Inject client and index from the destination
        dest = self.state.cyborgdb_destination
        if dest is not None:
            namespace["client"] = getattr(dest, "_client", None)
            namespace["index"] = getattr(dest, "_index", None)

        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        old_stdout, old_stderr = sys.stdout, sys.stderr
        try:
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            exec(code, namespace)  # noqa: S102
        except Exception as exc:
            stderr_capture.write(f"{type(exc).__name__}: {exc}\n")
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        out = stdout_capture.getvalue()
        err = stderr_capture.getvalue()

        if out:
            self.app.call_from_thread(log.write, out.rstrip("\n"))
        if err:
            self.app.call_from_thread(
                log.write, f"[red]{err.rstrip(chr(10))}[/red]"
            )

        self.app.call_from_thread(setattr, run_btn, "disabled", False)
