"""Platform implementations for crier."""

from .base import Platform, Article, PublishResult
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
