"""Dev.to platform implementation."""

from typing import Any

import requests

from .base import Article, Platform, PublishResult


class DevTo(Platform):
    """Dev.to publishing platform."""

    name = "devto"
    base_url = "https://dev.to/api"

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
        }

    def publish(self, article: Article) -> PublishResult:
        """Publish an article to dev.to."""
        data = {
            "article": {
                "title": article.title,
                "body_markdown": article.body,
                "published": article.published,
            }
        }

        if article.description:
            data["article"]["description"] = article.description
        if article.tags:
            data["article"]["tags"] = article.tags[:4]  # dev.to limit
        if article.canonical_url:
            data["article"]["canonical_url"] = article.canonical_url

        resp = requests.post(
            f"{self.base_url}/articles",
            headers=self.headers,
            json=data,
        )

        if resp.status_code == 201:
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
        """Update an existing article on dev.to."""
        data = {
            "article": {
                "body_markdown": article.body,
            }
        }

        if article.title:
            data["article"]["title"] = article.title
        if article.description:
            data["article"]["description"] = article.description
        if article.tags:
            data["article"]["tags"] = article.tags[:4]
        if article.canonical_url:
            data["article"]["canonical_url"] = article.canonical_url

        resp = requests.put(
            f"{self.base_url}/articles/{article_id}",
            headers=self.headers,
            json=data,
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
        """List your articles on dev.to."""
        resp = requests.get(
            f"{self.base_url}/articles/me",
            headers=self.headers,
            params={"per_page": limit},
        )

        if resp.status_code == 200:
            return resp.json()
        return []

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        """Get a specific article by ID."""
        resp = requests.get(
            f"{self.base_url}/articles/{article_id}",
            headers=self.headers,
        )

        if resp.status_code == 200:
            return resp.json()
        return None

    def delete(self, article_id: str) -> bool:
        """Delete an article (unpublish on dev.to)."""
        # dev.to doesn't have true delete, but we can unpublish
        resp = requests.put(
            f"{self.base_url}/articles/{article_id}",
            headers=self.headers,
            json={"article": {"published": False}},
        )
        return resp.status_code == 200
