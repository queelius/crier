"""WordPress platform implementation."""

import base64
from typing import Any

import requests

from .base import Article, Platform, PublishResult


class WordPress(Platform):
    """WordPress publishing platform (WordPress.com and self-hosted).

    API key formats:
    - WordPress.com: site.wordpress.com:access_token
    - Self-hosted: https://yoursite.com:username:app_password

    For self-hosted, create an Application Password in Users > Profile > Application Passwords.
    For WordPress.com, get an OAuth token from the WordPress.com developer portal.
    """

    name = "wordpress"

    def __init__(self, api_key: str):
        super().__init__(api_key)

        if api_key.startswith("https://"):
            # Self-hosted WordPress
            parts = api_key.split(":", 2)  # https, //site.com, user:pass
            if len(parts) < 3:
                raise ValueError(
                    "Self-hosted WordPress format: https://site.com:username:app_password"
                )
            # Reconstruct URL and get credentials
            url_part = f"{parts[0]}:{parts[1]}"  # https://site.com
            remaining = api_key[len(url_part) + 1:]  # username:app_password
            cred_parts = remaining.split(":", 1)
            if len(cred_parts) != 2:
                raise ValueError(
                    "Self-hosted WordPress format: https://site.com:username:app_password"
                )

            self.base_url = f"{url_part}/wp-json/wp/v2"
            self.username = cred_parts[0]
            self.password = cred_parts[1]
            self.is_wpcom = False

            # Basic auth header
            credentials = base64.b64encode(
                f"{self.username}:{self.password}".encode()
            ).decode()
            self.headers = {
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json",
            }
        else:
            # WordPress.com
            parts = api_key.split(":", 1)
            if len(parts) != 2:
                raise ValueError("WordPress.com format: site.wordpress.com:access_token")

            self.site = parts[0]
            self.access_token = parts[1]
            self.base_url = f"https://public-api.wordpress.com/wp/v2/sites/{self.site}"
            self.is_wpcom = True

            self.headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

    def publish(self, article: Article) -> PublishResult:
        """Publish a post to WordPress."""
        data: dict[str, Any] = {
            "title": article.title,
            "content": article.body,
            "status": "publish" if article.published else "draft",
        }

        if article.description:
            data["excerpt"] = article.description

        # Tags need to be tag IDs in WordPress, but we can pass names
        # and let WordPress create them (on self-hosted with appropriate permissions)
        if article.tags:
            data["tags"] = article.tags  # Will be created if they don't exist

        resp = requests.post(
            f"{self.base_url}/posts",
            headers=self.headers,
            json=data,
        )

        if resp.status_code in (200, 201):
            result = resp.json()
            return PublishResult(
                success=True,
                platform=self.name,
                article_id=str(result.get("id")),
                url=result.get("link"),
            )
        else:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"{resp.status_code}: {resp.text}",
            )

    def update(self, article_id: str, article: Article) -> PublishResult:
        """Update an existing post on WordPress."""
        data: dict[str, Any] = {
            "content": article.body,
        }

        if article.title:
            data["title"] = article.title
        if article.description:
            data["excerpt"] = article.description
        if article.tags:
            data["tags"] = article.tags

        resp = requests.post(
            f"{self.base_url}/posts/{article_id}",
            headers=self.headers,
            json=data,
        )

        if resp.status_code == 200:
            result = resp.json()
            return PublishResult(
                success=True,
                platform=self.name,
                article_id=str(result.get("id")),
                url=result.get("link"),
            )
        else:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"{resp.status_code}: {resp.text}",
            )

    def list_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        """List posts on WordPress."""
        params = {
            "per_page": limit,
            "status": "publish,draft",
        }

        resp = requests.get(
            f"{self.base_url}/posts",
            headers=self.headers,
            params=params,
        )

        if resp.status_code == 200:
            posts = resp.json()
            return [
                {
                    "id": p.get("id"),
                    "title": p.get("title", {}).get("rendered", ""),
                    "published": p.get("status") == "publish",
                    "url": p.get("link"),
                }
                for p in posts
            ]
        return []

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        """Get a specific post by ID."""
        resp = requests.get(
            f"{self.base_url}/posts/{article_id}",
            headers=self.headers,
        )

        if resp.status_code == 200:
            return resp.json()
        return None

    def delete(self, article_id: str) -> bool:
        """Delete (trash) a post on WordPress."""
        resp = requests.delete(
            f"{self.base_url}/posts/{article_id}",
            headers=self.headers,
        )
        return resp.status_code == 200
