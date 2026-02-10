from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_env_vars(value: str) -> str:
    """Expand ${VAR_NAME} patterns in a string using os.environ.

    Raises ValueError if a referenced variable is not set.
    """

    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        val = os.environ.get(var_name)
        if val is None:
            raise ValueError(
                f"Environment variable '{var_name}' is not set "
                f"(referenced in config as '${{{var_name}}}')"
            )
        return val

    return ENV_VAR_PATTERN.sub(replacer, value)


def _expand_recursive(obj: Any) -> Any:
    """Recursively expand env vars in strings within dicts/lists."""
    if isinstance(obj, str):
        return expand_env_vars(obj)
    if isinstance(obj, dict):
        return {k: _expand_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_recursive(item) for item in obj]
    return obj


@dataclass
class MigrationConfig:
    source_type: str = ""
    source_credentials: dict[str, str] = field(default_factory=dict)
    source_index: str = ""
    source_namespace: str | None = None

    destination_host: str = ""
    destination_api_key: str = ""

    create_index: bool = True
    index_name: str = ""
    index_type: str | None = None
    key_file: str | None = None
    index_key: str | None = None  # base64-encoded, for existing indexes

    batch_size: int = 100
    checkpoint_every: int = 10
    verify: bool = True
    spot_check_per_batch: int = 4


def load_config(path: str) -> MigrationConfig:
    """Parse a TOML config file, expand env vars, and return a MigrationConfig."""
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    raw = _expand_recursive(raw)

    config = MigrationConfig()

    # [source]
    source = raw.get("source", {})
    config.source_type = source.get("type", "")
    if not config.source_type:
        raise ValueError("Config missing [source].type")
    config.source_index = source.get("index", "")
    if not config.source_index:
        raise ValueError("Config missing [source].index")
    config.source_namespace = source.get("namespace")

    # All other source keys become credentials
    config.source_credentials = {
        k: v for k, v in source.items() if k not in ("type", "index", "namespace")
    }

    # [destination]
    dest = raw.get("destination", {})
    config.destination_host = dest.get("host", "")
    if not config.destination_host:
        raise ValueError("Config missing [destination].host")
    config.destination_api_key = dest.get("api_key", "")
    if not config.destination_api_key:
        raise ValueError("Config missing [destination].api_key")

    config.create_index = dest.get("create_index", True)
    config.index_name = dest.get("index_name", "")
    if not config.index_name:
        raise ValueError("Config missing [destination].index_name")
    config.index_type = dest.get("index_type")
    config.key_file = dest.get("key_file")
    config.index_key = dest.get("index_key")

    # [options]
    opts = raw.get("options", {})
    config.batch_size = opts.get("batch_size", 100)
    config.checkpoint_every = opts.get("checkpoint_every", 10)
    config.verify = opts.get("verify", True)
    config.spot_check_per_batch = opts.get("spot_check_per_batch", 4)

    return config
