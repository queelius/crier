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

    Returns True if the key is explicitly set to "manual" or "paste" (case-insensitive),
    meaning the platform is configured for copy-paste mode without API access.
    Returns False for None, empty string, or any other value.
    """
    if api_key is None:
        return False
    return api_key.lower() in ("manual", "paste")


def is_import_mode_key(api_key: str | None) -> bool:
    """Check if an API key value indicates import mode should be used.

    Returns True if the key is explicitly set to "import" (case-insensitive),
    meaning the platform supports importing from the canonical URL directly
    (like Medium's import feature).
    """
    if api_key is None:
        return False
    return api_key.lower() == "import"


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


def get_platform_mode(platform: str) -> str:
    """Get the mode for a platform.

    Returns:
        'api' - Platform has a real API key for automatic publishing
        'manual' - Platform is configured for copy-paste mode
        'import' - Platform uses URL import (like Medium)
        'unconfigured' - Platform has no configuration
    """
    api_key = get_api_key(platform)
    if api_key is None:
        return 'unconfigured'
    elif is_import_mode_key(api_key):
        return 'import'
    elif is_manual_mode_key(api_key):
        return 'manual'
    else:
        return 'api'


# Platforms with character limits that require content rewriting
SHORT_FORM_PLATFORMS = {'bluesky', 'mastodon', 'twitter', 'threads'}


def is_short_form_platform(platform: str) -> bool:
    """Check if platform has character limits requiring content rewrites."""
    return platform in SHORT_FORM_PLATFORMS


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


# Default exclude patterns for content discovery
# _index.md = Hugo section pages (branch bundles)
DEFAULT_EXCLUDE_PATTERNS = ["_index.md"]


def get_exclude_patterns() -> list[str]:
    """Get patterns to exclude from content discovery.

    Returns list of filename patterns to exclude.
    No default fallback - must be explicitly configured via `crier init`
    or manually in .crier/config.yaml.

    Configure in .crier/config.yaml:
        exclude_patterns:
          - _index.md
          - draft-*
    """
    config = load_local_config()
    return config.get("exclude_patterns", [])


def set_exclude_patterns(patterns: list[str]) -> None:
    """Set exclude patterns in repo-local config."""
    _save_local_config({"exclude_patterns": patterns})


def get_site_base_url() -> str | None:
    """Get the site base URL for canonical URL inference.

    This is used to auto-generate canonical_url when not specified in front matter.
    Configured in local .crier/config.yaml.
    """
    config = load_local_config()
    return config.get("site_base_url")


def set_site_base_url(url: str) -> None:
    """Set the site base URL in repo-local config."""
    # Normalize: remove trailing slash
    url = url.rstrip("/")
    _save_local_config({"site_base_url": url})


def infer_canonical_url(file_path: Path, content_root: Path, base_url: str) -> str:
    """Infer canonical URL from file path using Hugo conventions.

    Args:
        file_path: Path to the markdown file (e.g., content/post/2025-01-04-slug/index.md)
        content_root: Root of content directory (e.g., content/)
        base_url: Site base URL (e.g., https://metafunctor.com)

    Returns:
        Inferred canonical URL (e.g., https://metafunctor.com/post/2025-01-04-slug/)

    Hugo conventions:
    - content/post/slug/index.md -> /post/slug/
    - content/papers/name/index.md -> /papers/name/
    - content/about/_index.md -> /about/
    """
    file_path = Path(file_path).resolve()
    content_root = Path(content_root).resolve()

    # Get path relative to content root
    try:
        rel_path = file_path.relative_to(content_root)
    except ValueError:
        # File not under content_root, can't infer
        return f"{base_url}/{file_path.stem}/"

    # Convert path to URL:
    # content/post/2025-01-04-slug/index.md -> post/2025-01-04-slug/
    parts = list(rel_path.parts)

    # Remove index.md or _index.md from end
    if parts and parts[-1] in ("index.md", "_index.md"):
        parts = parts[:-1]
    elif parts and parts[-1].endswith(".md"):
        # file.md -> file/
        parts[-1] = parts[-1][:-3]

    url_path = "/".join(parts)
    return f"{base_url}/{url_path}/"


# Default file extensions for content discovery
DEFAULT_FILE_EXTENSIONS = [".md"]


def get_file_extensions() -> list[str]:
    """Get file extensions to scan for content.

    Returns list of extensions (with leading dot).
    Must be explicitly configured via `crier init` or manually.

    Configure in .crier/config.yaml:
        file_extensions:
          - .md
          - .mdx
    """
    config = load_local_config()
    return config.get("file_extensions", [])


def set_file_extensions(extensions: list[str]) -> None:
    """Set file extensions in repo-local config."""
    # Normalize: ensure leading dot
    normalized = [ext if ext.startswith(".") else f".{ext}" for ext in extensions]
    _save_local_config({"file_extensions": normalized})


def get_default_profile() -> str | None:
    """Get the default profile to use when no platform is specified.

    Configure in .crier/config.yaml:
        default_profile: blogs
    """
    config = load_local_config()
    return config.get("default_profile")


def set_default_profile(profile: str) -> None:
    """Set the default profile in repo-local config."""
    _save_local_config({"default_profile": profile})


def get_rewrite_author() -> str | None:
    """Get the default author for rewrites.

    When Claude or other tools generate short-form content,
    this author is used by default if --rewrite-author is not specified.

    Configure in .crier/config.yaml:
        rewrite_author: claude-code
    """
    config = load_local_config()
    return config.get("rewrite_author")


def set_rewrite_author(author: str) -> None:
    """Set the default rewrite author in repo-local config."""
    _save_local_config({"rewrite_author": author})


def get_llm_config() -> dict[str, Any]:
    """Get LLM configuration for auto-rewrite.

    LLM config is global only (stored in ~/.config/crier/config.yaml).
    Environment variables override config file values:
        - OPENAI_API_KEY: API key
        - OPENAI_BASE_URL: Base URL (defaults to https://api.openai.com/v1)

    Model is config-only (no env var) - defaults to gpt-4o-mini.

    Config structure in config.yaml:
        llm:
          api_key: sk-...  # API key (or use OPENAI_API_KEY env var)
          base_url: http://localhost:11434/v1  # For Ollama/custom endpoints
          model: llama3  # Model name (default: gpt-4o-mini)

    Returns:
        Dict with LLM config, or empty dict if not configured.
    """
    config = load_global_config()
    llm_config = config.get("llm", {})

    # Standard OpenAI environment variables override config file
    if env_key := os.environ.get("OPENAI_API_KEY"):
        llm_config["api_key"] = env_key

    if env_url := os.environ.get("OPENAI_BASE_URL"):
        llm_config["base_url"] = env_url

    # If we have an API key but no base_url, default to OpenAI
    if llm_config.get("api_key") and not llm_config.get("base_url"):
        llm_config["base_url"] = "https://api.openai.com/v1"

    # If we have an API key but no model, default to gpt-4o-mini (cheap/fast)
    if llm_config.get("api_key") and not llm_config.get("model"):
        llm_config["model"] = "gpt-4o-mini"

    return llm_config


def set_llm_config(
    provider: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    rewrite_prompt: str | None = None,
    temperature: float | None = None,
    retry_count: int | None = None,
    truncate_fallback: bool | None = None,
) -> None:
    """Set LLM configuration in global config.

    Only updates provided values, leaves others unchanged.
    """
    config = load_global_config()
    if "llm" not in config:
        config["llm"] = {}

    if provider is not None:
        config["llm"]["provider"] = provider
    if base_url is not None:
        config["llm"]["base_url"] = base_url
    if api_key is not None:
        config["llm"]["api_key"] = api_key
    if model is not None:
        config["llm"]["model"] = model
    if rewrite_prompt is not None:
        config["llm"]["rewrite_prompt"] = rewrite_prompt
    if temperature is not None:
        config["llm"]["temperature"] = temperature
    if retry_count is not None:
        config["llm"]["retry_count"] = retry_count
    if truncate_fallback is not None:
        config["llm"]["truncate_fallback"] = truncate_fallback

    save_config(config)


def is_llm_configured() -> bool:
    """Check if LLM is configured for auto-rewrite.

    Requires at minimum: base_url and model.
    """
    llm_config = get_llm_config()
    return bool(llm_config.get("base_url") and llm_config.get("model"))


def get_llm_temperature() -> float:
    """Get LLM temperature setting (default: 0.7)."""
    llm_config = get_llm_config()
    return float(llm_config.get("temperature", 0.7))


def get_llm_retry_count() -> int:
    """Get default retry count for auto-rewrite (default: 0)."""
    llm_config = get_llm_config()
    return int(llm_config.get("retry_count", 0))


def get_llm_truncate_fallback() -> bool:
    """Get default truncate fallback setting (default: False)."""
    llm_config = get_llm_config()
    return bool(llm_config.get("truncate_fallback", False))


def get_check_overrides() -> dict[str, str]:
    """Get check severity overrides from local config.

    Configure in .crier/config.yaml:
        checks:
          missing-title: error       # default
          missing-tags: disabled     # don't care about tags
          short-body: disabled       # allow short posts

    Returns:
        Dict mapping check_name to severity string (or "disabled").
    """
    config = load_local_config()
    return config.get("checks", {})
