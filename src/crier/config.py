"""Configuration management for crier."""

import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "crier"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"
LOCAL_CONFIG_DIR = ".crier"
LOCAL_CONFIG_FILE = "config.yaml"


def get_config_path() -> Path:
    """Get the global configuration file path."""
    return Path(os.environ.get("CRIER_CONFIG", DEFAULT_CONFIG_FILE))


def get_local_config_path(base_path: Path | None = None) -> Path:
    """Get the local (repo) configuration file path.

    Searches upward from base_path (or cwd) for a .crier directory,
    similar to how git finds .git directories.
    Returns the path where it would be created if not found.
    """
    if base_path is None:
        base_path = Path.cwd()

    # Search upward for existing .crier directory
    current = base_path.resolve()
    while current != current.parent:
        config_dir = current / LOCAL_CONFIG_DIR
        if config_dir.exists():
            return config_dir / LOCAL_CONFIG_FILE
        current = current.parent

    # Not found, use current directory
    return base_path / LOCAL_CONFIG_DIR / LOCAL_CONFIG_FILE


def find_local_config() -> Path | None:
    """Find existing local config by traversing upward. Returns None if not found."""
    path = get_local_config_path()
    return path if path.exists() else None


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


def is_manual_mode_key(api_key: str | None) -> bool:
    """Check if an API key value indicates manual mode should be used.

    Returns True if the key is explicitly set to "manual" (case-insensitive),
    meaning the platform is configured for copy-paste mode without API access.
    Returns False for None, empty string, or any other value.
    """
    if api_key is None:
        return False
    return api_key.lower() == "manual"


def is_platform_configured(platform: str) -> bool:
    """Check if a platform is configured (has any api_key entry, even if empty).

    This distinguishes between:
    - Platform not in config at all (not configured, user doesn't want to use it)
    - Platform in config with empty/manual key (configured for manual mode)
    - Platform in config with real key (configured for API mode)
    """
    # Check environment variable first
    env_key = f"CRIER_{platform.upper()}_API_KEY"
    if os.environ.get(env_key) is not None:
        return True

    # Check config file - platform section must exist with api_key
    config = load_config()
    platform_config = config.get("platforms", {}).get(platform, {})
    return "api_key" in platform_config


def get_api_key_source(platform: str) -> str | None:
    """Get the source of an API key.

    Returns:
        "env" if from environment variable
        "global" if from global config file
        None if not set
    """
    env_key = f"CRIER_{platform.upper()}_API_KEY"
    if os.environ.get(env_key):
        return "env"

    global_path = get_config_path()
    if global_path.exists():
        with open(global_path) as f:
            global_config = yaml.safe_load(f) or {}
        if global_config.get("platforms", {}).get(platform, {}).get("api_key"):
            return "global"

    return None


def load_global_config() -> dict[str, Any]:
    """Load only the global config (without merging local)."""
    global_path = get_config_path()
    if global_path.exists():
        with open(global_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def load_local_config() -> dict[str, Any]:
    """Load only the local config (without merging global)."""
    local_path = get_local_config_path()
    if local_path.exists():
        with open(local_path) as f:
            return yaml.safe_load(f) or {}
    return {}


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
