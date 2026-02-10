from textual.widgets import Static


class StepHeader(Static):
    """Header bar showing 'Step X of 6: Title'."""

    def __init__(self, step: int, title: str, total_steps: int = 6) -> None:
        super().__init__(f"Step {step} of {total_steps}: {title}")
        self.add_class("step-header")
