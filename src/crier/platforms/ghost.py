"""Ghost platform implementation."""

import hashlib
import hmac
import time
from typing import Any

from .base import Article, DeleteResult, Platform, PublishResult


class Ghost(Platform):
    """Ghost publishing platform.

    API key format: https://yourblog.com:admin_api_key
    Where admin_api_key is in format {id}:{secret} from Ghost Admin settings.
    """

    name = "ghost"
    description = "Self-hosted blogging"
    api_key_url = None  # Self-hosted, varies

    def __init__(self, api_key: str):
        super().__init__(api_key)
        # Parse: https://yourblog.com:id:secret
        parts = api_key.rsplit(":", 2)
        if len(parts) != 3:
            raise ValueError(
                "Ghost API key format: https://yourblog.com:key_id:key_secret"
            )
        self.base_url = parts[0].rstrip("/")
        self.key_id = parts[1]
        self.key_secret = parts[2]

    def _make_token(self) -> str:
        """Create a JWT token for Ghost Admin API."""
        import base64
        import json

        # Header
        header = {"alg": "HS256", "typ": "JWT", "kid": self.key_id}

        # Payload - token valid for 5 minutes
        now = int(time.time())
        payload = {
            "iat": now,
            "exp": now + 300,
            "aud": "/admin/",
        }

        # Encode
        def b64encode(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

        header_b64 = b64encode(json.dumps(header).encode())
        payload_b64 = b64encode(json.dumps(payload).encode())

        # Sign with the secret (hex-decoded)
        secret_bytes = bytes.fromhex(self.key_secret)
        message = f"{header_b64}.{payload_b64}".encode()
        signature = hmac.new(secret_bytes, message, hashlib.sha256).digest()
        signature_b64 = b64encode(signature)

        return f"{header_b64}.{payload_b64}.{signature_b64}"

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Ghost {self._make_token()}",
            "Content-Type": "application/json",
        }

    def publish(self, article: Article) -> PublishResult:
        """Publish an article to Ghost."""
        # Ghost uses mobiledoc or lexical format, but also accepts HTML
        # For markdown, we can use the html field with source format
        data = {
            "posts": [{
                "title": article.title,
                "html": article.body,  # Ghost can accept HTML/markdown here
                "status": "published" if article.published else "draft",
            }]
        }

        post = data["posts"][0]
        if article.description:
            post["custom_excerpt"] = article.description
        if article.tags:
            post["tags"] = [{"name": tag} for tag in article.tags]
        if article.canonical_url:
            post["canonical_url"] = article.canonical_url

        resp = self.retry_request(
            "post",
            f"{self.base_url}/ghost/api/admin/posts/",
            headers=self._get_headers(),
            json=data,
            params={"source": "html"},  # Tell Ghost we're sending HTML/markdown
        )

        if resp.status_code == 201:
            result = resp.json()
            post_data = result["posts"][0]
            return PublishResult(
                success=True,
                platform=self.name,
                article_id=post_data.get("id"),
                url=post_data.get("url"),
            )
        else:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"{resp.status_code}: {resp.text}",
            )

    def update(self, article_id: str, article: Article) -> PublishResult:
        """Update an existing article on Ghost."""
        # First get the current post to get updated_at (required for updates)
        current = self.get_article(article_id)
        if not current:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"Article {article_id} not found",
            )

        data = {
            "posts": [{
                "html": article.body,
                "updated_at": current.get("updated_at"),
            }]
        }

        post = data["posts"][0]
        if article.title:
            post["title"] = article.title
        if article.description:
            post["custom_excerpt"] = article.description
        if article.tags:
            post["tags"] = [{"name": tag} for tag in article.tags]
        if article.canonical_url:
            post["canonical_url"] = article.canonical_url

        resp = self.retry_request(
            "put",
            f"{self.base_url}/ghost/api/admin/posts/{article_id}/",
            headers=self._get_headers(),
            json=data,
            params={"source": "html"},
        )

        if resp.status_code == 200:
            result = resp.json()
            post_data = result["posts"][0]
            return PublishResult(
                success=True,
                platform=self.name,
                article_id=post_data.get("id"),
                url=post_data.get("url"),
            )
        else:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"{resp.status_code}: {resp.text}",
            )

    def list_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        """List posts on Ghost."""
        resp = self.retry_request(
            "get",
            f"{self.base_url}/ghost/api/admin/posts/",
            headers=self._get_headers(),
            params={"limit": limit},
        )

        if resp.status_code == 200:
            result = resp.json()
            posts = result.get("posts", [])
            return [
                {
                    "id": p.get("id"),
                    "title": p.get("title"),
                    "published": p.get("status") == "published",
                    "url": p.get("url"),
                }
                for p in posts
            ]
        return []

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        """Get a specific post by ID."""
        resp = self.retry_request(
            "get",
            f"{self.base_url}/ghost/api/admin/posts/{article_id}/",
            headers=self._get_headers(),
        )

        if resp.status_code == 200:
            result = resp.json()
            return result["posts"][0] if result.get("posts") else None
        return None

    def delete(self, article_id: str) -> DeleteResult:
        """Delete a post on Ghost."""
        resp = self.retry_request(
            "delete",
            f"{self.base_url}/ghost/api/admin/posts/{article_id}/",
            headers=self._get_headers(),
        )
        if resp.status_code == 204:
            return DeleteResult(success=True, platform=self.name)
        return DeleteResult(
            success=False,
            platform=self.name,
            error=f"{resp.status_code}: {resp.text}",
        )
