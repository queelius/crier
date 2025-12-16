"""Buttondown newsletter platform implementation."""

from typing import Any

import requests

from .base import Article, Platform, PublishResult


class Buttondown(Platform):
    """Buttondown newsletter platform.

    API key format: api_key
    Get your API key from https://buttondown.email/settings/programming
    """

    name = "buttondown"
    base_url = "https://api.buttondown.email/v1"

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.headers = {
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
        }

    def publish(self, article: Article) -> PublishResult:
        """Publish an email/newsletter to Buttondown."""
        data = {
            "subject": article.title,
            "body": article.body,
            "status": "published" if article.published else "draft",
        }

        if article.description:
            data["description"] = article.description

        resp = requests.post(
            f"{self.base_url}/emails",
            headers=self.headers,
            json=data,
        )

        if resp.status_code in (200, 201):
            result = resp.json()
            email_id = result.get("id")
            # Buttondown emails don't have direct URLs, use the web archive
            url = f"https://buttondown.email/archive/{email_id}" if email_id else None
            return PublishResult(
                success=True,
                platform=self.name,
                article_id=email_id,
                url=url,
            )
        else:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"{resp.status_code}: {resp.text}",
            )

    def update(self, article_id: str, article: Article) -> PublishResult:
        """Update an existing email on Buttondown."""
        data = {
            "body": article.body,
        }

        if article.title:
            data["subject"] = article.title
        if article.description:
            data["description"] = article.description

        resp = requests.patch(
            f"{self.base_url}/emails/{article_id}",
            headers=self.headers,
            json=data,
        )

        if resp.status_code == 200:
            result = resp.json()
            email_id = result.get("id")
            url = f"https://buttondown.email/archive/{email_id}" if email_id else None
            return PublishResult(
                success=True,
                platform=self.name,
                article_id=email_id,
                url=url,
            )
        else:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"{resp.status_code}: {resp.text}",
            )

    def list_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        """List emails on Buttondown."""
        resp = requests.get(
            f"{self.base_url}/emails",
            headers=self.headers,
            params={"page_size": limit},
        )

        if resp.status_code == 200:
            result = resp.json()
            # Buttondown returns paginated results
            emails = result.get("results", []) if isinstance(result, dict) else result
            return [
                {
                    "id": e.get("id"),
                    "title": e.get("subject"),
                    "published": e.get("status") == "published",
                    "url": f"https://buttondown.email/archive/{e.get('id')}",
                }
                for e in emails[:limit]
            ]
        return []

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        """Get a specific email by ID."""
        resp = requests.get(
            f"{self.base_url}/emails/{article_id}",
            headers=self.headers,
        )

        if resp.status_code == 200:
            return resp.json()
        return None

    def delete(self, article_id: str) -> bool:
        """Delete an email on Buttondown."""
        resp = requests.delete(
            f"{self.base_url}/emails/{article_id}",
            headers=self.headers,
        )
        return resp.status_code in (200, 204)
