"""Medium platform implementation.

Supports both API mode (with integration token) and manual mode.
"""

from typing import Any

import requests

from .base import Article, Platform, PublishResult


class Medium(Platform):
    """Medium publishing platform.

    API mode: Requires a Medium integration token.
    Get yours at: https://medium.com/me/settings/security

    Manual mode: Use --manual flag to generate content for copy-paste.
    """

    name = "medium"
    base_url = "https://api.medium.com/v1"
    compose_url = "https://medium.com/new-story"

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._user_id: str | None = None

    def format_for_manual(self, article: Article) -> str:
        """Format article for manual posting to Medium.

        Returns markdown with front matter stripped since Medium
        supports markdown directly in their editor.
        """
        parts = [f"# {article.title}"]

        if article.description:
            parts.append(f"*{article.description}*")

        parts.append("")  # blank line
        parts.append(article.body)

        if article.tags:
            parts.append("")
            parts.append("---")
            parts.append(f"Tags: {', '.join(article.tags[:5])}")

        if article.canonical_url:
            parts.append(f"Originally published at: {article.canonical_url}")

        return "\n".join(parts)

    def _get_user_id(self) -> str | None:
        """Get the authenticated user's ID."""
        if self._user_id:
            return self._user_id

        resp = requests.get(
            f"{self.base_url}/me",
            headers=self.headers,
        )

        if resp.status_code == 200:
            self._user_id = resp.json().get("data", {}).get("id")
            return self._user_id
        return None

    def publish(self, article: Article) -> PublishResult:
        """Publish an article to Medium."""
        user_id = self._get_user_id()
        if not user_id:
            return PublishResult(
                success=False,
                platform=self.name,
                error="Failed to authenticate with Medium",
            )

        data = {
            "title": article.title,
            "contentFormat": "markdown",
            "content": article.body,
            "publishStatus": "public" if article.published else "draft",
        }

        if article.tags:
            data["tags"] = article.tags[:5]  # Medium limit is 5 tags
        if article.canonical_url:
            data["canonicalUrl"] = article.canonical_url

        resp = requests.post(
            f"{self.base_url}/users/{user_id}/posts",
            headers=self.headers,
            json=data,
        )

        if resp.status_code == 201:
            result = resp.json().get("data", {})
            return PublishResult(
                success=True,
                platform=self.name,
                article_id=result.get("id"),
                url=result.get("url"),
            )
        else:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"{resp.status_code}: {resp.text}",
            )

    def update(self, article_id: str, article: Article) -> PublishResult:
        """Medium doesn't support updating posts via API."""
        return PublishResult(
            success=False,
            platform=self.name,
            error="Medium API does not support updating posts",
        )

    def list_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        """Medium API doesn't support listing posts."""
        return []

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        """Medium API doesn't support getting posts."""
        return None

    def delete(self, article_id: str) -> bool:
        """Medium API doesn't support deleting posts."""
        return False
