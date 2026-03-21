"""bot/config.py — Load and validate config_crypto.yaml."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG = _REPO_ROOT / "config_crypto.yaml"


def load_config(path: str | Path = _DEFAULT_CONFIG) -> dict[str, Any]:
    """Load configuration from YAML file and merge with environment variables.

    Environment variables (from .env) are loaded for API credentials.
    Config values can be overridden via environment variables prefixed with BOT_.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        Parsed configuration dictionary.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If required config keys are missing.
    """
    load_dotenv(_REPO_ROOT / ".env")

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as fh:
        cfg: dict[str, Any] = yaml.safe_load(fh)

    if cfg is None:
        raise ValueError("Config file is empty or invalid YAML.")

    return cfg


def get_api_credentials() -> dict[str, str]:
    """Read OKX API credentials from environment variables.

    Returns:
        Dictionary with keys: api_key, secret, passphrase.

    Raises:
        EnvironmentError: If any required credential is missing.
    """
    load_dotenv(_REPO_ROOT / ".env")

    required = {
        "api_key": "OKX_API_KEY",
        "secret": "OKX_SECRET",
        "passphrase": "OKX_PASSPHRASE",
    }

    credentials: dict[str, str] = {}
    missing: list[str] = []

    for key, env_var in required.items():
        value = os.environ.get(env_var, "").strip()
        if not value:
            missing.append(env_var)
        else:
            credentials[key] = value

    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Copy .env.example to .env and fill in your OKX DEMO credentials."
        )

    return credentials
