from __future__ import annotations

from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Input, Label

from cyborgdb_migrate.sources.base import CredentialField


class SourceForm(Vertical):
    """Dynamic credential form that renders fields from a SourceConnector."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._fields: list[CredentialField] = []
        self._inputs: dict[str, Input] = {}
        self._field_widgets: dict[str, list[Widget]] = {}

    async def rebuild(self, fields: list[CredentialField]) -> None:
        """Clear and rebuild the form with new credential fields."""
        self._fields = fields
        self._inputs.clear()
        self._field_widgets.clear()
        await self.remove_children()

        for field in fields:
            widgets: list[Widget] = []
            label = Label(f"{field.label}:")
            inp = Input(
                placeholder=field.default or "",
                password=field.is_secret,
                id=f"cred-{field.key}",
            )
            if field.default:
                inp.value = field.default

            self._inputs[field.key] = inp
            widgets.append(label)
            widgets.append(inp)
            self.mount(label)
            self.mount(inp)

            if field.help_text:
                help_label = Label(f"  {field.help_text}", classes="help-text")
                widgets.append(help_label)
                self.mount(help_label)

            self._field_widgets[field.key] = widgets

        self._apply_visibility()

    def get_values(self) -> dict[str, str]:
        """Return current field values."""
        return {key: inp.value for key, inp in self._inputs.items()}

    def on_input_changed(self, event: Input.Changed) -> None:
        """React to input changes for visible_when logic."""
        self._apply_visibility()

    def _apply_visibility(self) -> None:
        """Show/hide fields based on visible_when conditions."""
        current_values = self.get_values()
        for field in self._fields:
            if field.visible_when is None:
                continue
            visible = all(
                current_values.get(dep_key) == dep_value
                for dep_key, dep_value in field.visible_when.items()
            )
            for widget in self._field_widgets.get(field.key, []):
                widget.display = visible
