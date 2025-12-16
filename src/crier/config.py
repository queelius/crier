"""Configuration management for crier."""

import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "crier"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"


def get_config_path() -> Path:
    """Get the configuration file path."""
    return Path(os.environ.get("CRIER_CONFIG", DEFAULT_CONFIG_FILE))


def load_config() -> dict[str, Any]:
    """Load configuration from file."""
    config_path = get_config_path()
    if not config_path.exists():
        return {}

    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to file."""
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def get_api_key(platform: str) -> str | None:
    """Get API key for a platform.

    Checks in order:
    1. Environment variable: CRIER_{PLATFORM}_API_KEY
    2. Config file
    """
    # Check environment variable first
    env_key = f"CRIER_{platform.upper()}_API_KEY"
    if env_val := os.environ.get(env_key):
        return env_val

    # Fall back to config file
    config = load_config()
    return config.get("platforms", {}).get(platform, {}).get("api_key")


def set_api_key(platform: str, api_key: str) -> None:
    """Set API key for a platform in config file."""
    config = load_config()
    if "platforms" not in config:
        config["platforms"] = {}
    if platform not in config["platforms"]:
        config["platforms"][platform] = {}

    config["platforms"][platform]["api_key"] = api_key
    save_config(config)
