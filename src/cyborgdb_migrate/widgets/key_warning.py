from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


class KeyWarningModal(ModalScreen[bool]):
    """Modal requiring the user to type 'I understand' to acknowledge encryption key warning."""

    def __init__(self, key_hex: str) -> None:
        super().__init__()
        self._key_hex = key_hex

    def compose(self):
        with Vertical():
            yield Static("  IMPORTANT: Encryption Key", classes="warning-panel")
            yield Label("")
            yield Label("Your encryption key:")
            yield Label(f"  {self._key_hex}")
            yield Button("Copy Key", id="copy-key-btn", variant="default")
            yield Label("")
            yield Label("Copy this key now. We will not show it again.")
            yield Label("Without this key, your data is permanently")
            yield Label("unrecoverable.")
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
        if event.button.id == "copy-key-btn":
            self._copy_key()
        elif event.button.id == "cancel-btn":
            self.dismiss(False)
        elif event.button.id == "continue-btn":
            self.dismiss(True)

    def _copy_key(self) -> None:
        from cyborgdb_migrate.clipboard import copy_to_clipboard

        try:
            copy_to_clipboard(self._key_hex)
            self.notify("Key copied to clipboard")
        except Exception:
            self.notify("Copy failed — copy the key manually", severity="error")
