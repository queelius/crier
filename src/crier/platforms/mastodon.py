"""Mastodon platform implementation."""

from typing import Any

import requests

from .base import Article, Platform, PublishResult


class Mastodon(Platform):
    """Mastodon publishing platform.

    Requires instance URL and access token.
    api_key format: "instance_url:access_token" (e.g., "mastodon.social:token123")
    """

    name = "mastodon"
    max_content_length = 500  # Default Mastodon limit (some instances allow more)

    def __init__(self, api_key: str, instance: str | None = None):
        """Initialize with access token and instance.

        api_key should be in format: "instance:access_token"
        or just access_token if instance is provided separately.
        """
        super().__init__(api_key)

        if ":" in api_key and instance is None:
            self.instance, self.access_token = api_key.split(":", 1)
        else:
            self.instance = instance or "mastodon.social"
            self.access_token = api_key

        # Normalize instance URL
        if not self.instance.startswith("http"):
            self.instance = f"https://{self.instance}"

        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def publish(self, article: Article) -> PublishResult:
        """Post a toot to Mastodon.

        Creates a post with the article title/description and canonical URL.
        """
        # Create post text: title + description + URL
        text_parts = [article.title]
        if article.description:
            text_parts.append(article.description)
        if article.canonical_url:
            text_parts.append(article.canonical_url)

        # Add hashtags from tags
        if article.tags:
            hashtags = " ".join(f"#{tag.replace('-', '')}" for tag in article.tags[:5])
            text_parts.append(hashtags)

        text = "\n\n".join(text_parts)

        # Check content length
        if error := self._check_content_length(text):
            return PublishResult(
                success=False,
                platform=self.name,
                error=error,
            )

        data = {
            "status": text,
            "visibility": "public" if article.published else "private",
        }

        resp = requests.post(
            f"{self.instance}/api/v1/statuses",
            headers=self.headers,
            json=data,
        )

        if resp.status_code in (200, 201):
            result = resp.json()
            return PublishResult(
                success=True,
                platform=self.name,
                article_id=str(result.get("id")),
                url=result.get("url"),
            )
        else:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"{resp.status_code}: {resp.text}",
            )

    def update(self, article_id: str, article: Article) -> PublishResult:
        """Update an existing toot (Mastodon supports editing)."""
        text_parts = [article.title]
        if article.description:
            text_parts.append(article.description)
        if article.canonical_url:
            text_parts.append(article.canonical_url)

        text = "\n\n".join(text_parts)

        # Check content length
        if error := self._check_content_length(text):
            return PublishResult(
                success=False,
                platform=self.name,
                error=error,
            )

        resp = requests.put(
            f"{self.instance}/api/v1/statuses/{article_id}",
            headers=self.headers,
            json={"status": text},
        )

        if resp.status_code == 200:
            result = resp.json()
            return PublishResult(
                success=True,
                platform=self.name,
                article_id=str(result.get("id")),
                url=result.get("url"),
            )
        else:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"{resp.status_code}: {resp.text}",
            )

    def list_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        """List your recent toots."""
        # First get the account ID
        resp = requests.get(
            f"{self.instance}/api/v1/accounts/verify_credentials",
            headers=self.headers,
        )

        if resp.status_code != 200:
            return []

        account_id = resp.json().get("id")

        # Then get statuses
        resp = requests.get(
            f"{self.instance}/api/v1/accounts/{account_id}/statuses",
            headers=self.headers,
            params={"limit": limit},
        )

        if resp.status_code == 200:
            return [
                {
                    "id": status.get("id"),
                    "title": status.get("content", "")[:50],
                    "published": status.get("visibility") == "public",
                    "url": status.get("url"),
                }
                for status in resp.json()
            ]
        return []

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        """Get a specific toot by ID."""
        resp = requests.get(
            f"{self.instance}/api/v1/statuses/{article_id}",
            headers=self.headers,
        )

        if resp.status_code == 200:
            return resp.json()
        return None

    def delete(self, article_id: str) -> bool:
        """Delete a toot."""
        resp = requests.delete(
            f"{self.instance}/api/v1/statuses/{article_id}",
            headers=self.headers,
        )
        return resp.status_code == 200
