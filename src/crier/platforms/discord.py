"""Discord webhook platform implementation."""

from typing import Any

import requests

from .base import Article, Platform, PublishResult


class Discord(Platform):
    """Discord webhook publishing.

    API key format: webhook_url
    Create a webhook in Discord: Server Settings > Integrations > Webhooks
    The URL looks like: https://discord.com/api/webhooks/123456/abcdef...
    """

    name = "discord"

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.webhook_url = api_key
        if not self.webhook_url.startswith("https://discord.com/api/webhooks/"):
            raise ValueError(
                "Discord API key must be a webhook URL: "
                "https://discord.com/api/webhooks/..."
            )

    def _create_embed(self, article: Article) -> dict[str, Any]:
        """Create a Discord embed from an article."""
        embed: dict[str, Any] = {
            "title": article.title,
            "color": 5814783,  # A nice blue color
        }

        if article.description:
            embed["description"] = article.description

        if article.canonical_url:
            embed["url"] = article.canonical_url

        if article.tags:
            embed["footer"] = {
                "text": " • ".join(f"#{tag}" for tag in article.tags[:5])
            }

        return embed

    def publish(self, article: Article) -> PublishResult:
        """Send a message to Discord via webhook."""
        # Build message content
        content_parts = []
        if article.canonical_url:
            content_parts.append(f"📢 New post: **{article.title}**")
        else:
            content_parts.append(f"**{article.title}**")

        data: dict[str, Any] = {
            "content": "\n".join(content_parts) if content_parts else None,
            "embeds": [self._create_embed(article)],
        }

        # Add ?wait=true to get the message object back
        resp = requests.post(
            f"{self.webhook_url}?wait=true",
            json=data,
        )

        if resp.status_code == 200:
            result = resp.json()
            message_id = result.get("id")
            channel_id = result.get("channel_id")
            # Discord message URLs require guild ID which we don't have easily
            # Just return the message ID
            return PublishResult(
                success=True,
                platform=self.name,
                article_id=message_id,
                url=None,  # Webhook responses don't include full URL
            )
        else:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"{resp.status_code}: {resp.text}",
            )

    def update(self, article_id: str, article: Article) -> PublishResult:
        """Edit a webhook message on Discord."""
        content_parts = []
        if article.canonical_url:
            content_parts.append(f"📢 New post: **{article.title}**")
        else:
            content_parts.append(f"**{article.title}**")

        data: dict[str, Any] = {
            "content": "\n".join(content_parts) if content_parts else None,
            "embeds": [self._create_embed(article)],
        }

        resp = requests.patch(
            f"{self.webhook_url}/messages/{article_id}",
            json=data,
        )

        if resp.status_code == 200:
            result = resp.json()
            return PublishResult(
                success=True,
                platform=self.name,
                article_id=result.get("id"),
                url=None,
            )
        else:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"{resp.status_code}: {resp.text}",
            )

    def list_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        """Discord webhooks don't support listing messages."""
        return []

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        """Get a specific webhook message."""
        resp = requests.get(
            f"{self.webhook_url}/messages/{article_id}",
        )

        if resp.status_code == 200:
            return resp.json()
        return None

    def delete(self, article_id: str) -> bool:
        """Delete a webhook message on Discord."""
        resp = requests.delete(
            f"{self.webhook_url}/messages/{article_id}",
        )
        return resp.status_code == 204
