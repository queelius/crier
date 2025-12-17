"""Publication registry for tracking where content has been published."""

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REGISTRY_DIR = ".crier"
REGISTRY_FILE = "registry.yaml"


def get_registry_path(base_path: Path | None = None) -> Path:
    """Get the path to the registry file.

    Searches upward from base_path (or cwd) for a .crier directory,
    or creates one in the current directory if not found.
    """
    if base_path is None:
        base_path = Path.cwd()

    # Search upward for existing .crier directory
    current = base_path.resolve()
    while current != current.parent:
        registry_dir = current / REGISTRY_DIR
        if registry_dir.exists():
            return registry_dir / REGISTRY_FILE
        current = current.parent

    # Not found, use current directory
    return base_path / REGISTRY_DIR / REGISTRY_FILE


def load_registry(base_path: Path | None = None) -> dict[str, Any]:
    """Load the registry from disk."""
    registry_path = get_registry_path(base_path)

    if not registry_path.exists():
        return {"version": 1, "posts": {}}

    with open(registry_path) as f:
        data = yaml.safe_load(f) or {}

    # Ensure structure
    if "version" not in data:
        data["version"] = 1
    if "posts" not in data:
        data["posts"] = {}

    return data


def save_registry(registry: dict[str, Any], base_path: Path | None = None) -> None:
    """Save the registry to disk."""
    registry_path = get_registry_path(base_path)

    # Create directory if needed
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    with open(registry_path, "w") as f:
        yaml.dump(registry, f, default_flow_style=False, sort_keys=False)


def get_file_checksum(file_path: Path) -> str:
    """Calculate MD5 checksum of a file's content."""
    content = file_path.read_bytes()
    return hashlib.md5(content).hexdigest()[:12]


def get_relative_path(file_path: Path, base_path: Path | None = None) -> str:
    """Get the relative path of a file from the registry base."""
    if base_path is None:
        base_path = Path.cwd()

    file_path = Path(file_path).resolve()
    base_path = base_path.resolve()

    try:
        return str(file_path.relative_to(base_path))
    except ValueError:
        # File is outside base_path, use absolute path
        return str(file_path)


def record_publication(
    file_path: str | Path,
    platform: str,
    article_id: str | None,
    url: str | None,
    title: str | None = None,
    canonical_url: str | None = None,
    base_path: Path | None = None,
) -> None:
    """Record a successful publication to the registry."""
    file_path = Path(file_path).resolve()
    rel_path = get_relative_path(file_path, base_path)

    registry = load_registry(base_path)

    # Initialize post entry if needed
    if rel_path not in registry["posts"]:
        registry["posts"][rel_path] = {
            "title": title,
            "checksum": get_file_checksum(file_path),
            "canonical_url": canonical_url,
            "publications": {},
        }

    post = registry["posts"][rel_path]

    # Update metadata
    if title:
        post["title"] = title
    if canonical_url:
        post["canonical_url"] = canonical_url
    post["checksum"] = get_file_checksum(file_path)

    # Record this publication
    now = datetime.now(timezone.utc).isoformat()
    post["publications"][platform] = {
        "id": article_id,
        "url": url,
        "published_at": now,
        "updated_at": now,
    }

    save_registry(registry, base_path)


def get_post_status(file_path: str | Path, base_path: Path | None = None) -> dict[str, Any] | None:
    """Get the publication status for a specific file."""
    file_path = Path(file_path).resolve()
    rel_path = get_relative_path(file_path, base_path)

    registry = load_registry(base_path)
    return registry["posts"].get(rel_path)


def get_all_posts(base_path: Path | None = None) -> dict[str, Any]:
    """Get all tracked posts from the registry."""
    registry = load_registry(base_path)
    return registry.get("posts", {})


def is_published(file_path: str | Path, platform: str, base_path: Path | None = None) -> bool:
    """Check if a file has been published to a specific platform."""
    status = get_post_status(file_path, base_path)
    if not status:
        return False
    return platform in status.get("publications", {})


def get_publication_id(file_path: str | Path, platform: str, base_path: Path | None = None) -> str | None:
    """Get the article ID for a file on a specific platform."""
    status = get_post_status(file_path, base_path)
    if not status:
        return None
    pub = status.get("publications", {}).get(platform)
    return pub.get("id") if pub else None


def has_content_changed(file_path: str | Path, base_path: Path | None = None) -> bool:
    """Check if the file content has changed since last publication."""
    file_path = Path(file_path).resolve()
    status = get_post_status(file_path, base_path)

    if not status:
        return True  # Never published, consider it changed

    old_checksum = status.get("checksum")
    if not old_checksum:
        return True

    current_checksum = get_file_checksum(file_path)
    return current_checksum != old_checksum


def update_checksum(file_path: str | Path, base_path: Path | None = None) -> None:
    """Update the stored checksum for a file."""
    file_path = Path(file_path).resolve()
    rel_path = get_relative_path(file_path, base_path)

    registry = load_registry(base_path)

    if rel_path in registry["posts"]:
        registry["posts"][rel_path]["checksum"] = get_file_checksum(file_path)
        save_registry(registry, base_path)


def remove_post(file_path: str | Path, base_path: Path | None = None) -> bool:
    """Remove a post from the registry."""
    file_path = Path(file_path).resolve()
    rel_path = get_relative_path(file_path, base_path)

    registry = load_registry(base_path)

    if rel_path in registry["posts"]:
        del registry["posts"][rel_path]
        save_registry(registry, base_path)
        return True
    return False


def remove_publication(file_path: str | Path, platform: str, base_path: Path | None = None) -> bool:
    """Remove a single platform publication from the registry."""
    file_path = Path(file_path).resolve()
    rel_path = get_relative_path(file_path, base_path)

    registry = load_registry(base_path)

    if rel_path in registry["posts"]:
        publications = registry["posts"][rel_path].get("publications", {})
        if platform in publications:
            del publications[platform]
            save_registry(registry, base_path)
            return True
    return False
