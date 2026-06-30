from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest

from cyborgdb_migrate import version_check
from cyborgdb_migrate.version_check import (
    HealthUnreachable,
    VersionMismatch,
    _parse_minor,
    verify_server_version,
)


class _FakeResponse:
    def __init__(self, body: dict | str, status: int = 200) -> None:
        if isinstance(body, dict):
            payload = json.dumps(body).encode()
        else:
            payload = body.encode()
        self._buf = io.BytesIO(payload)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._buf.close()

    def read(self) -> bytes:
        return self._buf.read()


def _urlopen(body, status=200):
    """Build a patch context for urllib.request.urlopen."""
    return patch.object(
        version_check.urllib.request,
        "urlopen",
        return_value=_FakeResponse(body, status),
    )


def _urlopen_raises(exc):
    return patch.object(
        version_check.urllib.request, "urlopen", side_effect=exc
    )


class TestParseMinor:
    def test_basic(self):
        assert _parse_minor("0.16.2") == (0, 16)

    def test_with_v_prefix(self):
        assert _parse_minor("v0.16.2") == (0, 16)

    def test_dev_suffix(self):
        assert _parse_minor("0.16.2.dev0") == (0, 16)

    def test_rc_suffix(self):
        assert _parse_minor("0.16.2rc1") == (0, 16)

    def test_post_suffix(self):
        assert _parse_minor("0.16.2.post1") == (0, 16)

    def test_two_components(self):
        assert _parse_minor("1.2") == (1, 2)

    def test_unparseable(self):
        with pytest.raises(ValueError, match="unparseable"):
            _parse_minor("not-a-version")

    def test_empty(self):
        with pytest.raises(ValueError, match="unparseable"):
            _parse_minor("")


class TestVerifySameMinor:
    """AE1: same minor, patch differs → no raise."""

    def test_patch_differs_same_minor(self):
        with patch.object(version_check, "__version__", "0.16.2"), _urlopen(
            {"version": "0.16.3", "status": "healthy"}
        ):
            verify_server_version("http://localhost:8000")  # no raise

    def test_exact_match(self):
        with patch.object(version_check, "__version__", "0.16.2"), _urlopen(
            {"version": "0.16.2", "status": "healthy"}
        ):
            verify_server_version("http://localhost:8000")

    def test_dev_versions_compatible(self):
        with patch.object(version_check, "__version__", "0.16.2.dev0"), _urlopen(
            {"version": "0.16.2rc1"}
        ):
            verify_server_version("http://localhost:8000")


class TestVersionMismatch:
    """AE2 + AE3: minor mismatch (either direction) → VersionMismatch."""

    def test_server_newer_minor(self):
        with patch.object(version_check, "__version__", "0.16.2"), _urlopen(
            {"version": "0.17.0"}
        ):
            with pytest.raises(VersionMismatch) as excinfo:
                verify_server_version("http://localhost:8000")
            assert excinfo.value.server_version == "0.17.0"
            assert excinfo.value.migrate_version == "0.16.2"
            msg = str(excinfo.value)
            assert "0.17.0" in msg
            assert "0.16.2" in msg
            assert "pip install -U cyborgdb-migrate" in msg

    def test_server_older_minor(self):
        with patch.object(version_check, "__version__", "0.17.0"), _urlopen(
            {"version": "0.16.2"}
        ):
            with pytest.raises(VersionMismatch) as excinfo:
                verify_server_version("http://localhost:8000")
            assert excinfo.value.server_version == "0.16.2"
            assert excinfo.value.migrate_version == "0.17.0"

    def test_different_major(self):
        with patch.object(version_check, "__version__", "0.16.2"), _urlopen(
            {"version": "1.0.0"}
        ):
            with pytest.raises(VersionMismatch):
                verify_server_version("http://localhost:8000")


class TestHealthUnreachable:
    """AE4: /v1/health unreachable in various ways → HealthUnreachable."""

    def test_connection_refused(self):
        import urllib.error

        with _urlopen_raises(urllib.error.URLError("Connection refused")):
            with pytest.raises(HealthUnreachable) as excinfo:
                verify_server_version("http://localhost:9999")
            assert "localhost:9999" in str(excinfo.value)
            assert "network error" in str(excinfo.value)

    def test_http_404(self):
        import urllib.error

        err = urllib.error.HTTPError(
            url="http://h/v1/health", code=404, msg="NF", hdrs=None, fp=None
        )
        with _urlopen_raises(err):
            with pytest.raises(HealthUnreachable, match="HTTP 404"):
                verify_server_version("http://h")

    def test_http_500(self):
        import urllib.error

        err = urllib.error.HTTPError(
            url="http://h/v1/health", code=500, msg="ISE", hdrs=None, fp=None
        )
        with _urlopen_raises(err):
            with pytest.raises(HealthUnreachable, match="HTTP 500"):
                verify_server_version("http://h")

    def test_timeout(self):
        with _urlopen_raises(TimeoutError("timed out")):
            with pytest.raises(HealthUnreachable, match="connection error"):
                verify_server_version("http://h")

    def test_missing_version_field(self):
        with _urlopen({"status": "healthy"}):
            with pytest.raises(HealthUnreachable, match="missing 'version' field"):
                verify_server_version("http://h")

    def test_empty_version_field(self):
        with _urlopen({"version": "  "}):
            with pytest.raises(HealthUnreachable, match="'version' field is empty"):
                verify_server_version("http://h")

    def test_non_string_version_field(self):
        with _urlopen({"version": 123}):
            with pytest.raises(HealthUnreachable, match="'version' field is empty"):
                verify_server_version("http://h")

    def test_non_json_body(self):
        with _urlopen("not json at all"):
            with pytest.raises(HealthUnreachable, match="not valid JSON"):
                verify_server_version("http://h")

    def test_unparseable_version_string(self):
        with _urlopen({"version": "not-a-version"}):
            with pytest.raises(HealthUnreachable, match="unparseable"):
                verify_server_version("http://h")


class TestUrlConstruction:
    """The /v1/health URL is built correctly regardless of trailing slash."""

    def test_no_trailing_slash(self):
        with patch.object(version_check.urllib.request, "urlopen") as mock_open:
            mock_open.return_value = _FakeResponse({"version": "0.1.0"})
            with patch.object(version_check, "__version__", "0.1.0"):
                verify_server_version("http://localhost:8000")
        called_url = mock_open.call_args[0][0]
        assert called_url == "http://localhost:8000/v1/health"

    def test_trailing_slash(self):
        with patch.object(version_check.urllib.request, "urlopen") as mock_open:
            mock_open.return_value = _FakeResponse({"version": "0.1.0"})
            with patch.object(version_check, "__version__", "0.1.0"):
                verify_server_version("http://localhost:8000/")
        called_url = mock_open.call_args[0][0]
        assert called_url == "http://localhost:8000/v1/health"


def test_migrate_version_parses_on_import():
    """__version__ in the migrate package must be parseable."""
    from cyborgdb_migrate import __version__

    major, minor = _parse_minor(__version__)
    assert isinstance(major, int)
    assert isinstance(minor, int)
