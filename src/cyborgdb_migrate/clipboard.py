"""Cross-platform clipboard copy using native platform tools."""

from __future__ import annotations

import shutil
import subprocess
import sys


def copy_to_clipboard(text: str) -> None:
    """Copy text to the system clipboard.

    Uses pbcopy (macOS), xclip/xsel/wl-copy (Linux), or clip.exe (Windows).
    Raises RuntimeError if no clipboard tool is available.
    """
    if sys.platform == "darwin":
        cmd = ["pbcopy"]
    elif sys.platform == "linux":
        if shutil.which("xclip"):
            cmd = ["xclip", "-selection", "clipboard"]
        elif shutil.which("xsel"):
            cmd = ["xsel", "--clipboard", "--input"]
        elif shutil.which("wl-copy"):
            cmd = ["wl-copy"]
        else:
            raise RuntimeError(
                "No clipboard tool found. Install xclip, xsel, or wl-clipboard."
            )
    elif sys.platform == "win32":
        cmd = ["clip.exe"]
    else:
        raise RuntimeError(f"Clipboard not supported on {sys.platform}")

    subprocess.run(cmd, input=text.encode("utf-8"), check=True, capture_output=True, timeout=5)
