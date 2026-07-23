"""Shared helpers for the source→cyborgdb-service round-trip smoke tests."""

from __future__ import annotations

import textwrap
from pathlib import Path


def write_migrate_config(
    tmp_path: Path,
    source_block: str,
    service_url: str,
    dest_index_name: str,
    batch_size: int = 50,
    checkpoint_every: int = 5,
) -> Path:
    """Write a migrate TOML config.

    ``source_block`` is the full ``[source]`` section (including the header),
    already formatted for the connector under test. The ``[destination]`` and
    ``[options]`` sections are shared across every source.
    """
    config_path = tmp_path / "smoke.toml"
    config_path.write_text(
        textwrap.dedent(source_block).rstrip()
        + "\n\n"
        + textwrap.dedent(
            f"""\
            [destination]
            host = "{service_url}"
            # cyborgdb-service is started without CYBORGDB_SERVICE_ROOT_KEY, so
            # auth is disabled and any non-empty key is accepted. The config
            # layer rejects an empty api_key, so pass a placeholder.
            api_key = "smoke-no-auth"
            create_index = true
            index_name = "{dest_index_name}"

            [options]
            batch_size = {batch_size}
            checkpoint_every = {checkpoint_every}
            """
        )
    )
    return config_path


def run_migrate(config_path: Path, tmp_path: Path, batch_size: int = 50) -> None:
    """Run the headless migration.

    ``run_headless`` raises SystemExit(2) on spot-check failure, SystemExit(1)
    on other errors, and returns normally on success — so a clean return means
    the migration's own spot-check already passed.
    """
    from cyborgdb_migrate.cli import run_headless

    run_headless(
        str(config_path),
        batch_size=batch_size,
        resume=False,
        log_file=str(tmp_path / "smoke.log"),
        quiet=True,
    )


def assert_index_present(service_url: str, dest_index_name: str) -> None:
    """Verify the destination index exists via the cyborgdb SDK."""
    from cyborgdb import Client

    client = Client(base_url=service_url, api_key="")
    indexes = client.list_indexes()
    assert dest_index_name in indexes, (
        f"destination index '{dest_index_name}' missing from server; got {indexes}"
    )
