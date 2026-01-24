"""Base platform interface for crier."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utcnow() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


@dataclass
class ArticleStats:
    """Engagement statistics for an article on a platform."""

    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    reposts: int | None = None
    fetched_at: datetime = field(default_factory=_utcnow)


@dataclass
class DeleteResult:
    """Result of a delete operation."""

    success: bool
    platform: str
    error: str | None = None


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
    # Short description for the platforms command
    description: str = "Publishing platform"
    # Character limit for content (None means no limit)
    max_content_length: int | None = None
    # URL for manual compose page (e.g., https://twitter.com/compose/tweet)
    compose_url: str | None = None
    # URL to get API key/credentials
    api_key_url: str | None = None
    # Whether the platform supports deletion via API
    supports_delete: bool = True
    # Whether the platform supports engagement stats via API
    supports_stats: bool = False
    # Whether the platform supports thread posting
    supports_threads: bool = False
    # Maximum number of posts in a thread (if supports_threads)
    thread_max_posts: int = 25

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

    def delete(self, article_id: str) -> DeleteResult:
        """Delete an article from the platform.

        Returns DeleteResult with success status and optional error message.
        Subclasses should override if deletion is supported.
        """
        if not self.supports_delete:
            return DeleteResult(
                success=False,
                platform=self.name,
                error=f"{self.name} does not support deletion via API",
            )
        raise NotImplementedError(f"{self.name}.delete() not implemented")

    def get_stats(self, article_id: str) -> ArticleStats | None:
        """Fetch engagement statistics for an article.

        Returns ArticleStats if stats are available, None otherwise.
        Subclasses should override if stats are supported.
        """
        return None

    def publish_thread(self, posts: list[str]) -> "ThreadPublishResult":
        """Publish a thread of posts.

        Args:
            posts: List of post content strings (already formatted with thread indicators)

        Returns:
            ThreadPublishResult with success status and list of individual results.
            Subclasses should override if threading is supported.
        """
        if not self.supports_threads:
            return ThreadPublishResult(
                success=False,
                platform=self.name,
                error=f"{self.name} does not support thread posting",
            )
        raise NotImplementedError(f"{self.name}.publish_thread() not implemented")


@dataclass
class ThreadPublishResult:
    """Result of publishing a thread."""

    success: bool
    platform: str
    # ID of the first post (root of thread) - used as the main article_id
    root_id: str | None = None
    # URL of the first post
    root_url: str | None = None
    # All post IDs in order
    post_ids: list[str] | None = None
    # All post URLs in order
    post_urls: list[str] | None = None
    # Individual results for each post
    results: list[PublishResult] | None = None
    # Error message if failed
    error: str | None = None

    def publish_thread(self, posts: list[str]) -> list[PublishResult]:
        """Publish a thread of multiple posts.

        Args:
            posts: List of post content strings (already split and formatted)

        Returns:
            List of PublishResult, one for each post in the thread
        """
        raise NotImplementedError(f"{self.name} does not support thread posting")
