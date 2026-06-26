"""Server version compatibility check.

Compares the server's reported version (from ``GET /v1/health``) against
migrate's own ``__version__`` and refuses to run on a minor mismatch.
The supported range is "same minor": migrate ``vX.Y.*`` supports server
``vX.Y.*``. Patch drift inside a minor is allowed.

The check uses direct HTTP rather than going through the cyborgdb SDK
so that compatibility logic doesn't depend on a particular SDK version
exposing the response shape we need.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from cyborgdb_migrate import __version__

_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)")
_HEALTH_PATH = "/v1/health"
_DEFAULT_TIMEOUT_SECONDS = 10.0


class VersionMismatch(Exception):
    """The server's minor version is outside migrate's supported range."""

    def __init__(self, server_version: str, migrate_version: str) -> None:
        self.server_version = server_version
        self.migrate_version = migrate_version
        super().__init__(
            f"CyborgDB server is v{server_version}, but cyborgdb-migrate "
            f"v{migrate_version} only supports server v"
            f"{_format_minor(_parse_minor(migrate_version))}.*. "
            f"Upgrade migrate: pip install -U cyborgdb-migrate"
        )


class HealthUnreachable(Exception):
    """Could not retrieve a parseable server version from /v1/health."""

    def __init__(self, host: str, cause: str) -> None:
        self.host = host
        self.cause = cause
        super().__init__(
            f"Could not verify CyborgDB version at {host}: {cause}"
        )


def verify_server_version(
    host: str,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """Verify the server at *host* shares migrate's supported minor.

    Raises :class:`VersionMismatch` on minor mismatch or
    :class:`HealthUnreachable` when ``/v1/health`` cannot be read or
    parsed.
    """

    server_version = _fetch_server_version(host, timeout)

    try:
        server_minor = _parse_minor(server_version)
    except ValueError as exc:
        raise HealthUnreachable(host, str(exc)) from exc

        migrate_minor = _parse_minor(__version__)

    if server_minor != migrate_minor:
        raise VersionMismatch(
            server_version=server_version, migrate_version=__version__
        )


def _fetch_server_version(host: str, timeout: float) -> str:
    """Read the ``version`` field from ``{host}/v1/health``."""

    url = urllib.parse.urljoin(host.rstrip("/") + "/", _HEALTH_PATH.lstrip("/"))

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            status = getattr(response, "status", None)
            if status is not None and status != 200:
                raise HealthUnreachable(host, f"/v1/health returned HTTP {status}")
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise HealthUnreachable(host, f"/v1/health returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise HealthUnreachable(host, f"network error ({exc.reason})") from exc
    except (TimeoutError, OSError) as exc:
        raise HealthUnreachable(host, f"connection error ({exc})") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HealthUnreachable(host, "/v1/health response was not valid JSON") from exc

    if not isinstance(payload, dict) or "version" not in payload:
        raise HealthUnreachable(host, "/v1/health response missing 'version' field")

    version = payload["version"]
    if not isinstance(version, str) or not version.strip():
        raise HealthUnreachable(host, "/v1/health 'version' field is empty")

    return version.strip()


def _parse_minor(version: str) -> tuple[int, int]:
    """Parse ``vX.Y[.Z][...]`` into a ``(major, minor)`` tuple.

    Tolerates dev/rc/post suffixes on the patch component
    (``0.16.2.dev0``, ``0.16.2rc1``, ``0.16.2.post1``) — only major.minor
    affects compatibility.
    """

    match = _VERSION_RE.match(version)
    if not match:
        raise ValueError(f"unparseable version string '{version}'")
    return int(match.group(1)), int(match.group(2))


def _format_minor(minor: tuple[int, int]) -> str:
    return f"{minor[0]}.{minor[1]}"
