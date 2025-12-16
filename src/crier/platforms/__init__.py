"""Platform implementations for crier."""

from .base import Platform
from .devto import DevTo

# Registry of available platforms
PLATFORMS: dict[str, type[Platform]] = {
    "devto": DevTo,
}


def get_platform(name: str) -> type[Platform]:
    """Get a platform class by name."""
    if name not in PLATFORMS:
        available = ", ".join(PLATFORMS.keys())
        raise ValueError(f"Unknown platform: {name}. Available: {available}")
    return PLATFORMS[name]


__all__ = ["Platform", "DevTo", "PLATFORMS", "get_platform"]
