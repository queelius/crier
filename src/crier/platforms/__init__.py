"""Platform implementations for crier."""

from .base import Platform, Article, PublishResult
from .devto import DevTo
from .bluesky import Bluesky
from .mastodon import Mastodon
from .hashnode import Hashnode
from .medium import Medium
from .linkedin import LinkedIn

# Twitter requires optional dependency
try:
    from .twitter import Twitter
    _twitter_available = True
except ImportError:
    Twitter = None  # type: ignore
    _twitter_available = False

# Registry of available platforms
PLATFORMS: dict[str, type[Platform]] = {
    "devto": DevTo,
    "bluesky": Bluesky,
    "mastodon": Mastodon,
    "hashnode": Hashnode,
    "medium": Medium,
    "linkedin": LinkedIn,
}

if _twitter_available and Twitter is not None:
    PLATFORMS["twitter"] = Twitter


def get_platform(name: str) -> type[Platform]:
    """Get a platform class by name."""
    if name not in PLATFORMS:
        available = ", ".join(PLATFORMS.keys())
        raise ValueError(f"Unknown platform: {name}. Available: {available}")
    return PLATFORMS[name]


__all__ = [
    "Platform",
    "Article",
    "PublishResult",
    "DevTo",
    "Bluesky",
    "Mastodon",
    "Hashnode",
    "Medium",
    "LinkedIn",
    "Twitter",
    "PLATFORMS",
    "get_platform",
]
