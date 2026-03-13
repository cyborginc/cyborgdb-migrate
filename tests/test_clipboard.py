from unittest.mock import patch

import pytest

from cyborgdb_migrate.clipboard import copy_to_clipboard


class TestCopyToClipboard:
    @patch("cyborgdb_migrate.clipboard.sys")
    @patch("cyborgdb_migrate.clipboard.subprocess")
    def test_macos(self, mock_subprocess, mock_sys):
        mock_sys.platform = "darwin"
        copy_to_clipboard("hello")
        mock_subprocess.run.assert_called_once_with(
            ["pbcopy"], input=b"hello", check=True, capture_output=True, timeout=5
        )

    @patch("cyborgdb_migrate.clipboard.shutil")
    @patch("cyborgdb_migrate.clipboard.sys")
    @patch("cyborgdb_migrate.clipboard.subprocess")
    def test_linux_xclip(self, mock_subprocess, mock_sys, mock_shutil):
        mock_sys.platform = "linux"
        mock_shutil.which.side_effect = lambda cmd: "/usr/bin/xclip" if cmd == "xclip" else None
        copy_to_clipboard("hello")
        mock_subprocess.run.assert_called_once_with(
            ["xclip", "-selection", "clipboard"],
            input=b"hello", check=True, capture_output=True, timeout=5,
        )

    @patch("cyborgdb_migrate.clipboard.shutil")
    @patch("cyborgdb_migrate.clipboard.sys")
    def test_linux_no_tool(self, mock_sys, mock_shutil):
        mock_sys.platform = "linux"
        mock_shutil.which.return_value = None
        with pytest.raises(RuntimeError, match="No clipboard tool found"):
            copy_to_clipboard("hello")

    @patch("cyborgdb_migrate.clipboard.sys")
    @patch("cyborgdb_migrate.clipboard.subprocess")
    def test_windows(self, mock_subprocess, mock_sys):
        mock_sys.platform = "win32"
        copy_to_clipboard("hello")
        mock_subprocess.run.assert_called_once_with(
            ["clip.exe"], input=b"hello", check=True, capture_output=True, timeout=5
        )

    @patch("cyborgdb_migrate.clipboard.sys")
    def test_unsupported_platform(self, mock_sys):
        mock_sys.platform = "freebsd"
        with pytest.raises(RuntimeError, match="Clipboard not supported"):
            copy_to_clipboard("hello")
