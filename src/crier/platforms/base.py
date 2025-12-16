"""Base platform interface for crier."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class Article:
    """Represents an article to be published."""

    title: str
    body: str
    description: str | None = None
    tags: list[str] | None = None
    canonical_url: str | None = None
    published: bool = True

    # Platform-specific ID after publishing
    platform_id: str | None = None
    url: str | None = None


@dataclass
class PublishResult:
    """Result of a publish operation."""

    success: bool
    platform: str
    article_id: str | None = None
    url: str | None = None
    error: str | None = None


class Platform(ABC):
    """Abstract base class for publishing platforms."""

    name: str = "base"

    def __init__(self, api_key: str):
        self.api_key = api_key

    @abstractmethod
    def publish(self, article: Article) -> PublishResult:
        """Publish an article to the platform."""
        ...

    @abstractmethod
    def update(self, article_id: str, article: Article) -> PublishResult:
        """Update an existing article on the platform."""
        ...

    @abstractmethod
    def list_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        """List articles on the platform."""
        ...

    @abstractmethod
    def get_article(self, article_id: str) -> dict[str, Any] | None:
        """Get a specific article by ID."""
        ...

    def delete(self, article_id: str) -> bool:
        """Delete an article. Not all platforms support this."""
        raise NotImplementedError(f"{self.name} does not support article deletion")
