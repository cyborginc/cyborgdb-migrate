from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


class KeyWarningModal(ModalScreen[bool]):
    """Modal requiring the user to type 'I understand' to acknowledge encryption key warning."""

    def __init__(self, key_file_path: str) -> None:
        super().__init__()
        self._key_file_path = key_file_path

    def compose(self):
        with Vertical():
            yield Static("  IMPORTANT: Encryption Key", classes="warning-panel")
            yield Label("")
            yield Label(f"Your encryption key has been saved to:")
            yield Label(f"  {self._key_file_path}")
            yield Label("")
            yield Label("SAVE THIS FILE SECURELY.")
            yield Label("Without this key, your data is permanently")
            yield Label("unrecoverable. CyborgDB cannot recover it.")
            yield Label("")
            yield Label('Type "I understand" to continue:')
            yield Input(placeholder="I understand", id="confirm-input")
            yield Label("")
            with Horizontal(classes="button-row"):
                yield Button("Cancel", id="cancel-btn", variant="default")
                yield Button("Continue", id="continue-btn", variant="primary", disabled=True)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "confirm-input":
            btn = self.query_one("#continue-btn", Button)
            btn.disabled = event.value.strip().lower() != "i understand"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(False)
        elif event.button.id == "continue-btn":
            self.dismiss(True)
