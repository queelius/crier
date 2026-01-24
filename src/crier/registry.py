"""Publication registry for tracking where content has been published.

Registry Format v2:
- Keyed by canonical_url (stable identity)
- Tracks source_file for reference
- Uses SHA256 content hashes for change detection
"""

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REGISTRY_DIR = ".crier"
REGISTRY_FILE = "registry.yaml"
CURRENT_VERSION = 2


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


def get_content_hash(content: str) -> str:
    """Calculate SHA256 hash of content."""
    return "sha256:" + hashlib.sha256(content.encode()).hexdigest()[:16]


def get_file_content_hash(file_path: Path) -> str:
    """Calculate SHA256 hash of a file's content."""
    content = file_path.read_text()
    return get_content_hash(content)


def _migrate_v1_to_v2(v1_data: dict[str, Any]) -> dict[str, Any]:
    """Migrate v1 registry (file-path keys) to v2 (canonical_url keys)."""
    v2_data: dict[str, Any] = {
        "version": 2,
        "articles": {},
    }

    posts = v1_data.get("posts", {})
    for file_path, post_data in posts.items():
        canonical_url = post_data.get("canonical_url")

        if not canonical_url:
            # Can't migrate without canonical_url - skip
            continue

        # Convert publications to platforms format
        platforms = {}
        for platform_name, pub_data in post_data.get("publications", {}).items():
            platforms[platform_name] = {
                "id": pub_data.get("id"),
                "url": pub_data.get("url"),
                "published_at": pub_data.get("published_at"),
                "updated_at": pub_data.get("updated_at"),
            }

        v2_data["articles"][canonical_url] = {
            "title": post_data.get("title"),
            "source_file": file_path,
            "content_hash": None,  # Will be updated on next publish
            "platforms": platforms,
        }

    return v2_data


def load_registry(base_path: Path | None = None) -> dict[str, Any]:
    """Load the registry from disk, migrating if necessary."""
    registry_path = get_registry_path(base_path)

    if not registry_path.exists():
        return {"version": CURRENT_VERSION, "articles": {}}

    with open(registry_path) as f:
        data = yaml.safe_load(f) or {}

    version = data.get("version", 1)

    # Migrate v1 to v2
    if version == 1:
        data = _migrate_v1_to_v2(data)
        # Save migrated data
        save_registry(data, base_path)

    # Ensure structure
    if "articles" not in data:
        data["articles"] = {}
    data["version"] = CURRENT_VERSION

    return data


def save_registry(registry: dict[str, Any], base_path: Path | None = None) -> None:
    """Save the registry to disk."""
    registry_path = get_registry_path(base_path)

    # Create directory if needed
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure version is current
    registry["version"] = CURRENT_VERSION

    with open(registry_path, "w") as f:
        yaml.dump(registry, f, default_flow_style=False, sort_keys=False)


def record_publication(
    canonical_url: str,
    platform: str,
    article_id: str | None,
    url: str | None,
    title: str | None = None,
    source_file: str | Path | None = None,
    content_hash: str | None = None,
    rewritten: bool = False,
    rewrite_author: str | None = None,
    posted_content: str | None = None,
    base_path: Path | None = None,
) -> None:
    """Record a successful publication to the registry.

    Args:
        canonical_url: The canonical URL of the source article (primary key)
        platform: Platform name (e.g., 'bluesky', 'mastodon')
        article_id: Platform-specific article ID
        url: URL of the published article on the platform
        title: Article title
        source_file: Path to the source file (for reference)
        content_hash: Hash of the source content
        rewritten: Whether content was rewritten for this platform
        rewrite_author: Who rewrote the content (e.g., 'claude-code')
        posted_content: The actual content posted (for short-form platforms)
        base_path: Base path for registry lookup
    """
    registry = load_registry(base_path)

    # Initialize article entry if needed
    if canonical_url not in registry["articles"]:
        registry["articles"][canonical_url] = {
            "title": title,
            "source_file": str(source_file) if source_file else None,
            "content_hash": content_hash,
            "platforms": {},
        }

    article = registry["articles"][canonical_url]

    # Update metadata
    if title:
        article["title"] = title
    if source_file:
        article["source_file"] = str(source_file)
    if content_hash:
        article["content_hash"] = content_hash

    # Record this publication
    now = datetime.now(timezone.utc).isoformat()
    platform_data: dict[str, Any] = {
        "id": article_id,
        "url": url,
        "published_at": now,
        "updated_at": now,
        "content_hash": content_hash,
    }

    # Track rewrites
    if rewritten:
        platform_data["rewritten"] = True
        if rewrite_author:
            platform_data["rewrite_author"] = rewrite_author
        if posted_content:
            platform_data["posted_content"] = posted_content

    article["platforms"][platform] = platform_data
    save_registry(registry, base_path)


def get_article(canonical_url: str, base_path: Path | None = None) -> dict[str, Any] | None:
    """Get an article by canonical URL."""
    registry = load_registry(base_path)
    return registry["articles"].get(canonical_url)


def get_article_by_file(file_path: str | Path, base_path: Path | None = None) -> tuple[str, dict[str, Any]] | None:
    """Find an article by its source file path.

    Returns (canonical_url, article_data) or None if not found.
    """
    registry = load_registry(base_path)
    file_path_str = str(file_path)

    for canonical_url, article in registry["articles"].items():
        if article.get("source_file") == file_path_str:
            return (canonical_url, article)

    return None


def get_all_articles(base_path: Path | None = None) -> dict[str, Any]:
    """Get all tracked articles from the registry."""
    registry = load_registry(base_path)
    return registry.get("articles", {})


def get_platform_publications(platform: str, base_path: Path | None = None) -> list[dict[str, Any]]:
    """Get all publications for a specific platform.

    Returns list of dicts with canonical_url, title, and platform-specific data.
    """
    registry = load_registry(base_path)
    results = []

    for canonical_url, article in registry.get("articles", {}).items():
        if platform in article.get("platforms", {}):
            platform_data = article["platforms"][platform]
            results.append({
                "canonical_url": canonical_url,
                "title": article.get("title"),
                "source_file": article.get("source_file"),
                "platform_id": platform_data.get("id"),
                "platform_url": platform_data.get("url"),
                "published_at": platform_data.get("published_at"),
                "rewritten": platform_data.get("rewritten", False),
                "rewrite_author": platform_data.get("rewrite_author"),
            })

    return results


def is_published(canonical_url: str, platform: str, base_path: Path | None = None) -> bool:
    """Check if an article has been published to a specific platform."""
    article = get_article(canonical_url, base_path)
    if not article:
        return False
    return platform in article.get("platforms", {})


def get_publication_id(canonical_url: str, platform: str, base_path: Path | None = None) -> str | None:
    """Get the platform-specific article ID."""
    article = get_article(canonical_url, base_path)
    if not article:
        return None
    pub = article.get("platforms", {}).get(platform)
    return pub.get("id") if pub else None


def get_publication_info(
    canonical_url: str, platform: str, base_path: Path | None = None
) -> dict[str, Any] | None:
    """Get full publication info for a platform.

    Returns dict with: article_id, url, published_at, content_hash, etc.
    """
    article = get_article(canonical_url, base_path)
    if not article:
        return None
    platform_data = article.get("platforms", {}).get(platform)
    if not platform_data:
        return None
    # Normalize the "id" key to "article_id" for consistency
    return {
        "article_id": platform_data.get("id"),
        "url": platform_data.get("url"),
        "published_at": platform_data.get("published_at"),
        "updated_at": platform_data.get("updated_at"),
        "content_hash": platform_data.get("content_hash"),
        "rewritten": platform_data.get("rewritten", False),
        "rewrite_author": platform_data.get("rewrite_author"),
    }


def has_content_changed(
    canonical_url: str,
    current_hash: str,
    platform: str | None = None,
    base_path: Path | None = None,
) -> bool:
    """Check if content has changed since last publication.

    Args:
        canonical_url: The article's canonical URL
        current_hash: Current content hash
        platform: If specified, check against when posted to this platform.
                  If None, check against the article's stored hash.
    """
    article = get_article(canonical_url, base_path)
    if not article:
        return True  # New article, consider changed

    if platform:
        platform_data = article.get("platforms", {}).get(platform)
        if not platform_data:
            return True  # Never published to this platform
        old_hash = platform_data.get("content_hash")
    else:
        old_hash = article.get("content_hash")

    if not old_hash:
        return True  # No hash stored

    return current_hash != old_hash


def remove_article(canonical_url: str, base_path: Path | None = None) -> bool:
    """Remove an article from the registry."""
    registry = load_registry(base_path)

    if canonical_url in registry["articles"]:
        del registry["articles"][canonical_url]
        save_registry(registry, base_path)
        return True
    return False


def remove_publication(canonical_url: str, platform: str, base_path: Path | None = None) -> bool:
    """Remove a single platform publication from the registry."""
    registry = load_registry(base_path)

    if canonical_url in registry["articles"]:
        platforms = registry["articles"][canonical_url].get("platforms", {})
        if platform in platforms:
            del platforms[platform]
            save_registry(registry, base_path)
            return True
    return False


def record_deletion(
    canonical_url: str,
    platform: str,
    base_path: Path | None = None,
) -> bool:
    """Record that a publication was deleted from a platform.

    Instead of removing the record, we mark it with deleted_at timestamp.
    This preserves history and prevents re-publishing.

    Returns True if the deletion was recorded, False if not found.
    """
    registry = load_registry(base_path)

    if canonical_url not in registry["articles"]:
        return False

    article = registry["articles"][canonical_url]
    if platform not in article.get("platforms", {}):
        return False

    # Mark as deleted instead of removing
    now = datetime.now(timezone.utc).isoformat()
    article["platforms"][platform]["deleted_at"] = now
    save_registry(registry, base_path)
    return True


def is_deleted(canonical_url: str, platform: str, base_path: Path | None = None) -> bool:
    """Check if a publication has been deleted from a platform."""
    article = get_article(canonical_url, base_path)
    if not article:
        return False

    platform_data = article.get("platforms", {}).get(platform)
    if not platform_data:
        return False

    return "deleted_at" in platform_data


def set_archived(
    canonical_url: str,
    archived: bool = True,
    base_path: Path | None = None,
) -> bool:
    """Set the archived status of an article.

    Archived articles are excluded from audit --publish by default.

    Returns True if the status was changed, False if article not found.
    """
    registry = load_registry(base_path)

    if canonical_url not in registry["articles"]:
        return False

    article = registry["articles"][canonical_url]
    if archived:
        article["archived"] = True
        article["archived_at"] = datetime.now(timezone.utc).isoformat()
    else:
        article.pop("archived", None)
        article.pop("archived_at", None)

    save_registry(registry, base_path)
    return True


def is_archived(canonical_url: str, base_path: Path | None = None) -> bool:
    """Check if an article is archived."""
    article = get_article(canonical_url, base_path)
    if not article:
        return False
    return article.get("archived", False)


def save_stats(
    canonical_url: str,
    platform: str,
    views: int | None = None,
    likes: int | None = None,
    comments: int | None = None,
    reposts: int | None = None,
    base_path: Path | None = None,
) -> bool:
    """Save engagement stats for a publication.

    Stats are cached in the registry to avoid excessive API calls.

    Returns True if stats were saved, False if publication not found.
    """
    registry = load_registry(base_path)

    if canonical_url not in registry["articles"]:
        return False

    article = registry["articles"][canonical_url]
    if platform not in article.get("platforms", {}):
        return False

    now = datetime.now(timezone.utc).isoformat()
    article["platforms"][platform]["stats"] = {
        "views": views,
        "likes": likes,
        "comments": comments,
        "reposts": reposts,
        "fetched_at": now,
    }
    save_registry(registry, base_path)
    return True


def get_cached_stats(
    canonical_url: str,
    platform: str,
    base_path: Path | None = None,
) -> dict[str, Any] | None:
    """Get cached stats for a publication.

    Returns dict with views, likes, comments, reposts, fetched_at.
    Returns None if no stats cached or publication not found.
    """
    article = get_article(canonical_url, base_path)
    if not article:
        return None

    platform_data = article.get("platforms", {}).get(platform)
    if not platform_data:
        return None

    return platform_data.get("stats")


def get_stats_age_seconds(
    canonical_url: str,
    platform: str,
    base_path: Path | None = None,
) -> float | None:
    """Get the age of cached stats in seconds.

    Returns None if no stats cached.
    """
    stats = get_cached_stats(canonical_url, platform, base_path)
    if not stats or "fetched_at" not in stats:
        return None

    fetched_at = datetime.fromisoformat(stats["fetched_at"])
    now = datetime.now(timezone.utc)
    return (now - fetched_at).total_seconds()


def record_thread_publication(
    canonical_url: str,
    platform: str,
    root_id: str | None,
    root_url: str | None,
    thread_ids: list[str],
    thread_urls: list[str] | None = None,
    title: str | None = None,
    source_file: str | Path | None = None,
    content_hash: str | None = None,
    rewritten: bool = False,
    rewrite_author: str | None = None,
    base_path: Path | None = None,
) -> None:
    """Record a thread publication to the registry.

    Similar to record_publication but stores thread-specific data.

    Args:
        canonical_url: The canonical URL of the source article
        platform: Platform name (e.g., 'bluesky', 'mastodon')
        root_id: ID of the first (root) post
        root_url: URL of the first (root) post
        thread_ids: List of all post IDs in the thread
        thread_urls: List of all post URLs in the thread
        title: Article title
        source_file: Path to the source file
        content_hash: Hash of the source content
        rewritten: Whether content was rewritten
        rewrite_author: Who rewrote the content
        base_path: Base path for registry lookup
    """
    registry = load_registry(base_path)

    # Initialize article entry if needed
    if canonical_url not in registry["articles"]:
        registry["articles"][canonical_url] = {
            "title": title,
            "source_file": str(source_file) if source_file else None,
            "content_hash": content_hash,
            "platforms": {},
        }

    article = registry["articles"][canonical_url]

    # Update metadata
    if title:
        article["title"] = title
    if source_file:
        article["source_file"] = str(source_file)
    if content_hash:
        article["content_hash"] = content_hash

    # Record this thread publication
    now = datetime.now(timezone.utc).isoformat()
    platform_data: dict[str, Any] = {
        "id": root_id,  # Use root_id as main ID
        "url": root_url,
        "published_at": now,
        "updated_at": now,
        "content_hash": content_hash,
        "is_thread": True,
        "thread_ids": thread_ids,
    }

    if thread_urls:
        platform_data["thread_urls"] = thread_urls

    if rewritten:
        platform_data["rewritten"] = True
        if rewrite_author:
            platform_data["rewrite_author"] = rewrite_author

    article["platforms"][platform] = platform_data
    save_registry(registry, base_path)


def is_thread(canonical_url: str, platform: str, base_path: Path | None = None) -> bool:
    """Check if a publication is a thread."""
    article = get_article(canonical_url, base_path)
    if not article:
        return False

    platform_data = article.get("platforms", {}).get(platform)
    if not platform_data:
        return False

    return platform_data.get("is_thread", False)


def get_thread_ids(
    canonical_url: str,
    platform: str,
    base_path: Path | None = None,
) -> list[str] | None:
    """Get the list of post IDs for a thread publication.

    Returns None if not a thread or not found.
    """
    article = get_article(canonical_url, base_path)
    if not article:
        return None

    platform_data = article.get("platforms", {}).get(platform)
    if not platform_data:
        return None

    return platform_data.get("thread_ids")


