"""Configuration management for crier."""

import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "crier"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"
LOCAL_CONFIG_FILE = Path(".crier") / "config.yaml"


def get_config_path() -> Path:
    """Get the global configuration file path."""
    return Path(os.environ.get("CRIER_CONFIG", DEFAULT_CONFIG_FILE))


def get_local_config_path() -> Path:
    """Get the local (repo) configuration file path."""
    return LOCAL_CONFIG_FILE


def load_config() -> dict[str, Any]:
    """Load configuration, merging local and global configs.

    Local config (.crier/config.yaml) takes precedence for content_paths and profiles.
    Global config (~/.config/crier/config.yaml) is used for API keys.
    Environment variables override everything for API keys.
    """
    config: dict[str, Any] = {}

    # Load global config first (for API keys)
    global_path = get_config_path()
    if global_path.exists():
        with open(global_path) as f:
            config = yaml.safe_load(f) or {}

    # Merge local config (for content_paths, profiles)
    local_path = get_local_config_path()
    if local_path.exists():
        with open(local_path) as f:
            local_config = yaml.safe_load(f) or {}
            # Local content_paths and profiles override global
            if "content_paths" in local_config:
                config["content_paths"] = local_config["content_paths"]
            if "profiles" in local_config:
                # Merge profiles, local takes precedence
                config.setdefault("profiles", {})
                config["profiles"].update(local_config["profiles"])

    return config


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


def get_profile(name: str) -> list[str] | None:
    """Get a profile (list of platforms) by name.

    Profiles can reference other profiles for composition.
    """
    config = load_config()
    profiles = config.get("profiles", {})

    if name not in profiles:
        return None

    platforms = profiles[name]

    # Expand nested profile references
    expanded = []
    for item in platforms:
        if item in profiles:
            # This is a reference to another profile
            nested = get_profile(item)
            if nested:
                expanded.extend(nested)
        else:
            expanded.append(item)

    # Remove duplicates while preserving order
    seen = set()
    result = []
    for p in expanded:
        if p not in seen:
            seen.add(p)
            result.append(p)

    return result


def set_profile(name: str, platforms: list[str]) -> None:
    """Set a profile in config file."""
    config = load_config()
    if "profiles" not in config:
        config["profiles"] = {}

    config["profiles"][name] = platforms
    save_config(config)


def get_all_profiles() -> dict[str, list[str]]:
    """Get all defined profiles."""
    config = load_config()
    return config.get("profiles", {})


def get_content_paths() -> list[str]:
    """Get configured content paths.

    Returns list of directories to scan for content.
    Can be relative or absolute paths.
    """
    config = load_config()
    return config.get("content_paths", [])


def _save_local_config(config_data: dict[str, Any]) -> None:
    """Save configuration to local .crier/config.yaml."""
    local_path = get_local_config_path()
    local_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing local config
    existing: dict[str, Any] = {}
    if local_path.exists():
        with open(local_path) as f:
            existing = yaml.safe_load(f) or {}

    # Merge new data
    existing.update(config_data)

    with open(local_path, "w") as f:
        yaml.dump(existing, f, default_flow_style=False)


def set_content_paths(paths: list[str]) -> None:
    """Set content paths in repo-local config (.crier/config.yaml)."""
    _save_local_config({"content_paths": paths})


def add_content_path(path: str) -> None:
    """Add a content path to repo-local config."""
    paths = get_content_paths()
    if path not in paths:
        paths.append(path)
    set_content_paths(paths)


def remove_content_path(path: str) -> bool:
    """Remove a content path from repo-local config. Returns True if removed."""
    paths = get_content_paths()
    if path in paths:
        paths.remove(path)
        set_content_paths(paths)
        return True
    return False
