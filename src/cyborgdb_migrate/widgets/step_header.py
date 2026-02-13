from textual.containers import Vertical
from textual.widgets import Static


class StepHeader(Vertical):
    """Compact header showing step progress dots and step title."""

    DEFAULT_CSS = """
    StepHeader {
        dock: top;
        height: auto;
        padding: 1 1 0 1;
        align: center top;
    }

    StepHeader > Static {
        text-align: center;
        width: 100%;
    }
    """

    def __init__(self, step: int, title: str, total_steps: int = 7) -> None:
        super().__init__()
        self._step = step
        self._title = title
        self._total_steps = total_steps

    def compose(self):
        # Step dots
        parts = []
        for i in range(1, self._total_steps + 1):
            if i < self._step:
                parts.append("[#56D3DB]\u25cf[/]")
            elif i == self._step:
                parts.append("[bold #69F1F6]\u25cf[/]")
            else:
                parts.append("[dim]\u25cb[/]")

            if i < self._total_steps:
                if i < self._step:
                    parts.append("[#56D3DB]\u2500\u2500[/]")
                else:
                    parts.append("[dim]\u2500\u2500[/]")

        yield Static("".join(parts))

        # Step title
        yield Static(f"[bold]{self._title}[/]")
