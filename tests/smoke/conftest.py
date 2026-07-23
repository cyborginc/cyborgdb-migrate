"""docker-compose lifecycle for the smoke tests.

Brings up cyborgdb-service (the migration destination) plus one container per
supported source DB, waits for every service to answer its HTTP readiness
endpoint *from the host*, yields the connection URLs, and tears down at exit.

Readiness is polled host-side on purpose: the modern source images (chromadb
1.x especially) ship no python/curl/wget, so a Docker in-container HEALTHCHECK
can't run. The test runner has python and can reach the mapped ports, so we
poll from here instead of trusting `docker inspect ... .State.Health`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

COMPOSE_FILE = Path(__file__).parent / "docker-compose.yml"
READY_TIMEOUT_SECONDS = 240

# service label -> readiness URL (host side). Milvus is slowest to come up.
READINESS = {
    "cyborgdb-service": "http://localhost:8000/v1/health",
    "chromadb": "http://localhost:8001/api/v2/heartbeat",
    "qdrant": "http://localhost:6333/readyz",
    "weaviate": "http://localhost:8080/v1/.well-known/ready",
    "milvus": "http://localhost:9091/healthz",
}


def _compose_cmd() -> list[str]:
    """Resolve docker compose (plugin) or docker-compose (legacy)."""
    if shutil.which("docker") is not None:
        return ["docker", "compose"]
    if shutil.which("docker-compose") is not None:
        return ["docker-compose"]
    pytest.skip("docker / docker compose is not available")


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def _endpoint_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def _dump_diagnostics(compose: list[str]) -> str:
    """Capture compose ps + logs so a readiness timeout is debuggable in CI."""
    parts = []
    for label, sub in (("ps", ["ps"]), ("logs", ["logs", "--tail", "80"])):
        result = subprocess.run(
            compose + ["-f", str(COMPOSE_FILE)] + sub,
            capture_output=True,
            text=True,
        )
        parts.append(f"===== docker compose {label} =====\n{result.stdout}\n{result.stderr}")
    return "\n".join(parts)


def _wait_for_all_ready(compose: list[str]) -> None:
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    pending = dict(READINESS)
    while time.monotonic() < deadline:
        for label in list(pending):
            if _endpoint_ready(pending[label]):
                del pending[label]
        if not pending:
            return
        time.sleep(3)
    raise RuntimeError(
        f"Timed out after {READY_TIMEOUT_SECONDS}s waiting for: "
        f"{sorted(pending)}\n\n{_dump_diagnostics(compose)}"
    )


@pytest.fixture(scope="session")
def smoke_stack():
    if not os.environ.get("CYBORGDB_SERVICE_TAG"):
        pytest.skip(
            "CYBORGDB_SERVICE_TAG is unset — set it to a published "
            "cyborginc/cyborgdb-service tag (e.g. '0.17.0') to run the smoke."
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
        pytest.fail(f"docker compose up failed:\nstdout: {exc.stdout}\nstderr: {exc.stderr}")

    try:
        _wait_for_all_ready(compose)
        yield {
            "service_url": "http://localhost:8000",
            # chromadb host port — compose maps host 8001 → container 8000.
            "chromadb_host": "localhost",
            "chromadb_port": 8001,
            "qdrant_url": "http://localhost:6333",
            "weaviate_host": "localhost",
            "weaviate_http_port": 8080,
            "weaviate_grpc_port": 50051,
            "milvus_uri": "http://localhost:19530",
        }
    finally:
        subprocess.run(
            compose + ["-f", str(COMPOSE_FILE), "down", "--remove-orphans", "-v"],
            capture_output=True,
            text=True,
        )
