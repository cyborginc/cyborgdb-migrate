"""docker-compose lifecycle for the smoke test.

Spins up `cyborgdb-service` at the version pinned by
``CYBORGDB_SERVICE_TAG`` and a sibling ChromaDB container, waits for both
to report healthy, yields the connection URLs, and tears down at exit.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

COMPOSE_FILE = Path(__file__).parent / "docker-compose.yml"
HEALTH_TIMEOUT_SECONDS = 120


def _compose_cmd() -> list[str]:
    """Resolve docker compose (plugin) or docker-compose (legacy)."""
    if shutil.which("docker") is not None:
        # Prefer the v2 plugin form when docker CLI is present.
        return ["docker", "compose"]
    if shutil.which("docker-compose") is not None:
        return ["docker-compose"]
    pytest.skip("docker / docker compose is not available")


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def _container_state(container: str) -> dict:
    """Return the inspect JSON for one container, or {} when missing."""
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{json .State}}", container],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {}
    import json

    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return {}


def _wait_for_healthy(containers: list[str]) -> None:
    deadline = time.monotonic() + HEALTH_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        all_healthy = True
        for c in containers:
            state = _container_state(c)
            status = state.get("Health", {}).get("Status")
            if status != "healthy":
                all_healthy = False
                break
        if all_healthy:
            return
        time.sleep(2)
    raise RuntimeError(
        f"Timed out waiting {HEALTH_TIMEOUT_SECONDS}s for containers to become "
        f"healthy: {containers}"
    )


@pytest.fixture(scope="session")
def smoke_stack():
    if not os.environ.get("CYBORGDB_SERVICE_TAG"):
        pytest.skip(
            "CYBORGDB_SERVICE_TAG is unset — set it to a published "
            "cyborginc/cyborgdb-service tag (e.g. '0.16.2') to run the smoke."
        )

    compose = _compose_cmd()

    # Pre-clean any leftover containers from a prior failed run.
    subprocess.run(
        compose + ["-f", str(COMPOSE_FILE), "down", "--remove-orphans", "-v"],
        capture_output=True,
        text=True,
    )

    try:
        _run(compose + ["-f", str(COMPOSE_FILE), "up", "-d"])
    except subprocess.CalledProcessError as exc:
        pytest.fail(
            "docker compose up failed:\n"
            f"stdout: {exc.stdout}\nstderr: {exc.stderr}"
        )

    try:
        _wait_for_healthy(["smoke-cyborgdb-service", "smoke-chromadb"])
        yield {
            "service_url": "http://localhost:8000",
            # ChromaDB host port — note compose maps host 8001 → container 8000
            "chromadb_host": "localhost",
            "chromadb_port": 8001,
        }
    finally:
        subprocess.run(
            compose + ["-f", str(COMPOSE_FILE), "down", "--remove-orphans", "-v"],
            capture_output=True,
            text=True,
        )
