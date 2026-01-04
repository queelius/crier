"""Twitter/X platform implementation (manual/copy-paste mode).

Twitter's API requires complex OAuth setup and elevated access.
This implementation generates tweet text for manual posting with confirmation.
"""

from typing import Any

from .base import Article, Platform, PublishResult


class Twitter(Platform):
    """Twitter/X manual mode.

    Generates formatted tweet text that you copy and paste into Twitter.
    The CLI will ask for confirmation before recording to registry.

    No API key required - use any placeholder value.
    """

    name = "twitter"
    max_content_length = 280  # Twitter character limit
    compose_url = "https://twitter.com/compose/tweet"

    def __init__(self, api_key: str):
        """API key is ignored - this is manual mode."""
        super().__init__(api_key)

    def format_for_manual(self, article: Article) -> str:
        """Format article as a tweet for manual posting."""
        parts = [article.title]

        if article.tags:
            hashtags = " ".join(f"#{tag.replace('-', '_')}" for tag in article.tags[:3])
            parts.append(hashtags)

        if article.canonical_url:
            parts.append(article.canonical_url)

        return "\n\n".join(parts)

    def publish(self, article: Article) -> PublishResult:
        """Return manual mode result for CLI to handle confirmation.

        The CLI will display the content, copy to clipboard, open browser,
        and ask user to confirm before recording to registry.
        """
        tweet = self.format_for_manual(article)

        # Check content length
        if error := self._check_content_length(tweet):
            return PublishResult(
                success=False,
                platform=self.name,
                error=error,
            )

        # Return result that signals CLI to handle manual confirmation
        return PublishResult(
            success=True,
            platform=self.name,
            article_id=None,  # Will be set after user confirms
            url=None,  # User provides after posting
            requires_confirmation=True,
            manual_content=tweet,
            compose_url=self.compose_url,
        )

    def update(self, article_id: str, article: Article) -> PublishResult:
        """Twitter doesn't support editing - generate new tweet."""
        return PublishResult(
            success=False,
            platform=self.name,
            error="Twitter doesn't support editing tweets. Delete and repost manually.",
        )

    def list_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        """Not available in manual mode."""
        return []

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        """Not available in manual mode."""
        return None

    def delete(self, article_id: str) -> bool:
        """Not available in manual mode."""
        raise NotImplementedError("Manual mode - delete tweets at twitter.com")
