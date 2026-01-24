"""Platform implementations for crier."""

from .base import Platform, Article, PublishResult, DeleteResult, ArticleStats, ThreadPublishResult
from .devto import DevTo
from .bluesky import Bluesky
from .mastodon import Mastodon
from .hashnode import Hashnode
from .medium import Medium
from .linkedin import LinkedIn
from .ghost import Ghost
from .buttondown import Buttondown
from .telegram import Telegram
from .discord import Discord
from .threads import Threads
from .wordpress import WordPress
from .twitter import Twitter

# Registry of available platforms
PLATFORMS: dict[str, type[Platform]] = {
    "devto": DevTo,
    "bluesky": Bluesky,
    "mastodon": Mastodon,
    "hashnode": Hashnode,
    "medium": Medium,
    "linkedin": LinkedIn,
    "ghost": Ghost,
    "buttondown": Buttondown,
    "telegram": Telegram,
    "discord": Discord,
    "threads": Threads,
    "wordpress": WordPress,
    "twitter": Twitter,
}


def get_platform(name: str) -> type[Platform]:
    """Get a platform class by name."""
    if name not in PLATFORMS:
        from difflib import get_close_matches

        # Suggest closest match
        suggestions = get_close_matches(name, PLATFORMS.keys(), n=1, cutoff=0.6)
        available = ", ".join(sorted(PLATFORMS.keys()))

        error_msg = f"Unknown platform: {name}"
        if suggestions:
            error_msg += f"\nDid you mean: {suggestions[0]}?"
        error_msg += f"\n\nAvailable platforms: {available}"
        raise ValueError(error_msg)
    return PLATFORMS[name]


__all__ = [
    "Platform",
    "Article",
    "PublishResult",
    "DeleteResult",
    "ArticleStats",
    "ThreadPublishResult",
    "DevTo",
    "Bluesky",
    "Mastodon",
    "Hashnode",
    "Medium",
    "LinkedIn",
    "Ghost",
    "Buttondown",
    "Telegram",
    "Discord",
    "Threads",
    "WordPress",
    "Twitter",
    "PLATFORMS",
    "get_platform",
]
