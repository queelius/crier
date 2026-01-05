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
    cover_image: str | None = None

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
    # Manual mode fields - when set, CLI should handle confirmation flow
    requires_confirmation: bool = False
    manual_content: str | None = None
    compose_url: str | None = None


class Platform(ABC):
    """Abstract base class for publishing platforms."""

    name: str = "base"
    # Character limit for content (None means no limit)
    max_content_length: int | None = None
    # URL for manual compose page (e.g., https://twitter.com/compose/tweet)
    compose_url: str | None = None

    def __init__(self, api_key: str):
        self.api_key = api_key

    def format_for_manual(self, article: Article) -> str:
        """Format article content for manual posting.

        Override in subclasses for platform-specific formatting.
        Default: returns full body for long-form platforms.
        """
        return article.body

    def _check_content_length(self, content: str) -> str | None:
        """Check if content exceeds platform limit.

        Returns error message if too long, None if OK.
        """
        if self.max_content_length is None:
            return None

        if len(content) > self.max_content_length:
            return (
                f"Content too long for {self.name}: {len(content)} characters "
                f"(limit: {self.max_content_length}). "
                f"Use --rewrite to provide a shorter version for {self.name}."
            )
        return None

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
