"""Dev.to platform implementation."""

from typing import Any

import requests

from .base import Article, ArticleStats, DeleteResult, Platform, PublishResult


def sanitize_tags(tags: list[str]) -> list[str]:
    """Sanitize tags for DevTo requirements.

    DevTo tags must be:
    - Alphanumeric only (no hyphens, spaces, special chars)
    - Lowercase
    - Max 4 tags
    - Non-empty
    """
    sanitized = []
    for tag in tags:
        # Remove hyphens, spaces, and other non-alphanumeric chars
        clean = "".join(c for c in tag.lower() if c.isalnum())
        # Skip empty strings (e.g., tag "---" becomes "")
        if clean and clean not in sanitized:
            sanitized.append(clean)
            if len(sanitized) >= 4:  # DevTo limit
                break
    return sanitized


class DevTo(Platform):
    """Dev.to publishing platform."""

    name = "devto"
    description = "Developer blogging platform"
    base_url = "https://dev.to/api"
    api_key_url = "https://dev.to/settings/extensions"
    supports_stats = True

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
            data["article"]["tags"] = sanitize_tags(article.tags)
        if article.canonical_url:
            data["article"]["canonical_url"] = article.canonical_url

        resp = requests.post(
            f"{self.base_url}/articles",
            headers=self.headers,
            json=data,
            timeout=30,
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
            data["article"]["tags"] = sanitize_tags(article.tags)
        if article.canonical_url:
            data["article"]["canonical_url"] = article.canonical_url

        resp = requests.put(
            f"{self.base_url}/articles/{article_id}",
            headers=self.headers,
            json=data,
            timeout=30,
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
            timeout=30,
        )

        if resp.status_code == 200:
            return resp.json()
        return []

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        """Get a specific article by ID."""
        resp = requests.get(
            f"{self.base_url}/articles/{article_id}",
            headers=self.headers,
            timeout=30,
        )

        if resp.status_code == 200:
            return resp.json()
        return None

    def delete(self, article_id: str) -> DeleteResult:
        """Delete an article (unpublish on dev.to).

        Note: dev.to doesn't have true delete, but we can unpublish.
        """
        resp = requests.put(
            f"{self.base_url}/articles/{article_id}",
            headers=self.headers,
            json={"article": {"published": False}},
            timeout=30,
        )
        if resp.status_code == 200:
            return DeleteResult(success=True, platform=self.name)
        return DeleteResult(
            success=False,
            platform=self.name,
            error=f"{resp.status_code}: {resp.text}",
        )

    def get_stats(self, article_id: str) -> ArticleStats | None:
        """Get article statistics from dev.to.

        Dev.to provides:
        - page_views_count: Total views
        - public_reactions_count: Likes/reactions
        - comments_count: Number of comments
        """
        article = self.get_article(article_id)
        if not article:
            return None

        return ArticleStats(
            views=article.get("page_views_count"),
            likes=article.get("public_reactions_count"),
            comments=article.get("comments_count"),
        )
