from pathlib import Path

from rich.text import Text

_LOGO_RAW = (Path(__file__).parent.parent / "cyborgdb_ascii.txt").read_text()


def _colorize_logo(raw: str) -> Text:
    """Color the ASCII art: '+' chars teal (circle icon), '*' chars white (text)."""
    # Pad all lines to equal width so text-align: center works uniformly
    lines = raw.rstrip("\n").split("\n")
    max_width = max(len(line) for line in lines)
    padded = "\n".join(line.ljust(max_width) for line in lines)

    text = Text()
    for char in padded:
        if char == "+":
            text.append(char, style="#56D3DB")
        elif char == "*":
            text.append(char, style="bold")
        else:
            text.append(char)
    return text


LOGO = _colorize_logo(_LOGO_RAW)
