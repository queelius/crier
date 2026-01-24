"""Threads (Meta) platform implementation."""

import time
from typing import Any

import requests

from .base import Article, DeleteResult, Platform, PublishResult


class Threads(Platform):
    """Threads (Meta) publishing platform.

    API key format: user_id:access_token
    Requires a Meta/Instagram Business account with Threads API access.
    Get credentials from Meta Developer Portal.
    """

    name = "threads"
    description = "Short posts (500 chars)"
    base_url = "https://graph.threads.net/v1.0"
    max_content_length = 500  # Threads character limit
    api_key_url = "https://developers.facebook.com/"
    supports_delete = False
    supports_stats = True

    def __init__(self, api_key: str):
        super().__init__(api_key)
        parts = api_key.split(":", 1)
        if len(parts) != 2:
            raise ValueError("Threads API key format: user_id:access_token")
        self.user_id = parts[0]
        self.access_token = parts[1]

    def _format_post(self, article: Article) -> str:
        """Format article for Threads."""
        parts = [article.title]

        if article.description:
            parts.append(f"\n\n{article.description}")

        if article.canonical_url:
            parts.append(f"\n\n🔗 {article.canonical_url}")

        if article.tags:
            hashtags = " ".join(f"#{tag.replace('-', '_')}" for tag in article.tags[:3])
            parts.append(f"\n\n{hashtags}")

        return "".join(parts)

    def publish(self, article: Article) -> PublishResult:
        """Publish a post to Threads (two-step process)."""
        text = self._format_post(article)

        # Check content length
        if error := self._check_content_length(text):
            return PublishResult(
                success=False,
                platform=self.name,
                error=error,
            )

        # Step 1: Create media container
        create_params = {
            "media_type": "TEXT",
            "text": text,
            "access_token": self.access_token,
        }

        resp = requests.post(
            f"{self.base_url}/{self.user_id}/threads",
            params=create_params,
            timeout=30,
        )

        if resp.status_code != 200:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"Container creation failed: {resp.status_code}: {resp.text}",
            )

        result = resp.json()
        creation_id = result.get("id")

        if not creation_id:
            return PublishResult(
                success=False,
                platform=self.name,
                error="No creation_id returned",
            )

        # Brief wait for container to be ready
        time.sleep(1)

        # Step 2: Publish the container
        publish_params = {
            "creation_id": creation_id,
            "access_token": self.access_token,
        }

        resp = requests.post(
            f"{self.base_url}/{self.user_id}/threads_publish",
            params=publish_params,
            timeout=30,
        )

        if resp.status_code == 200:
            result = resp.json()
            post_id = result.get("id")
            # Threads URLs are like: https://www.threads.net/@username/post/{post_id}
            # We don't have username easily, so skip URL
            return PublishResult(
                success=True,
                platform=self.name,
                article_id=post_id,
                url=None,
            )
        else:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"Publish failed: {resp.status_code}: {resp.text}",
            )

    def update(self, article_id: str, article: Article) -> PublishResult:
        """Threads doesn't support editing posts."""
        return PublishResult(
            success=False,
            platform=self.name,
            error="Threads does not support editing posts",
        )

    def list_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        """List user's Threads posts."""
        params = {
            "fields": "id,text,timestamp,permalink",
            "limit": limit,
            "access_token": self.access_token,
        }

        resp = requests.get(
            f"{self.base_url}/{self.user_id}/threads",
            params=params,
            timeout=30,
        )

        if resp.status_code == 200:
            result = resp.json()
            posts = result.get("data", [])
            return [
                {
                    "id": p.get("id"),
                    "title": (p.get("text") or "")[:50],
                    "published": True,
                    "url": p.get("permalink"),
                }
                for p in posts
            ]
        return []

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        """Get a specific Threads post."""
        params = {
            "fields": "id,text,timestamp,permalink",
            "access_token": self.access_token,
        }

        resp = requests.get(
            f"{self.base_url}/{article_id}",
            params=params,
            timeout=30,
        )

        if resp.status_code == 200:
            return resp.json()
        return None

    def delete(self, article_id: str) -> DeleteResult:
        """Threads API doesn't support deleting posts via API."""
        return DeleteResult(
            success=False,
            platform=self.name,
            error="Threads API does not support deleting posts. Delete manually at threads.net",
        )
