"""Bluesky platform implementation using AT Protocol."""

from datetime import datetime, timezone
from typing import Any

import requests

from .base import Article, Platform, PublishResult


class Bluesky(Platform):
    """Bluesky publishing platform.

    Uses the AT Protocol for posting.
    Requires: handle (e.g., user.bsky.social) and app password.
    """

    name = "bluesky"
    base_url = "https://bsky.social/xrpc"
    max_content_length = 300  # Bluesky character limit

    def __init__(self, api_key: str, handle: str | None = None):
        """Initialize with app password and handle.

        api_key should be in format: "handle:app_password"
        or just app_password if handle is provided separately.
        """
        super().__init__(api_key)

        if ":" in api_key and handle is None:
            self.handle, self.app_password = api_key.split(":", 1)
        else:
            self.handle = handle or ""
            self.app_password = api_key

        self.session = None
        self.did = None

    def _create_session(self) -> bool:
        """Create an authenticated session."""
        resp = requests.post(
            f"{self.base_url}/com.atproto.server.createSession",
            json={
                "identifier": self.handle,
                "password": self.app_password,
            },
        )

        if resp.status_code == 200:
            data = resp.json()
            self.session = data.get("accessJwt")
            self.did = data.get("did")
            return True
        return False

    def _get_headers(self) -> dict[str, str]:
        """Get authenticated headers."""
        if not self.session:
            self._create_session()

        return {
            "Authorization": f"Bearer {self.session}",
            "Content-Type": "application/json",
        }

    def publish(self, article: Article) -> PublishResult:
        """Post to Bluesky.

        Creates a post with the article title/description and canonical URL.
        """
        # Create post text: title + description + URL
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

        if not self._create_session():
            return PublishResult(
                success=False,
                platform=self.name,
                error="Failed to authenticate with Bluesky",
            )

        record = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }

        # Add link card if canonical_url exists
        if article.canonical_url:
            record["embed"] = {
                "$type": "app.bsky.embed.external",
                "external": {
                    "uri": article.canonical_url,
                    "title": article.title,
                    "description": article.description or "",
                },
            }

        resp = requests.post(
            f"{self.base_url}/com.atproto.repo.createRecord",
            headers=self._get_headers(),
            json={
                "repo": self.did,
                "collection": "app.bsky.feed.post",
                "record": record,
            },
        )

        if resp.status_code == 200:
            data = resp.json()
            uri = data.get("uri", "")
            # Convert AT URI to web URL
            # at://did:plc:xxx/app.bsky.feed.post/yyy -> https://bsky.app/profile/handle/post/yyy
            post_id = uri.split("/")[-1] if uri else ""
            url = f"https://bsky.app/profile/{self.handle}/post/{post_id}"

            return PublishResult(
                success=True,
                platform=self.name,
                article_id=uri,
                url=url,
            )
        else:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"{resp.status_code}: {resp.text}",
            )

    def update(self, article_id: str, article: Article) -> PublishResult:
        """Bluesky doesn't support editing posts."""
        return PublishResult(
            success=False,
            platform=self.name,
            error="Bluesky does not support editing posts",
        )

    def list_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        """List recent posts."""
        if not self._create_session():
            return []

        resp = requests.get(
            f"{self.base_url}/app.bsky.feed.getAuthorFeed",
            headers=self._get_headers(),
            params={"actor": self.did, "limit": limit},
        )

        if resp.status_code == 200:
            data = resp.json()
            results = []
            for item in data.get("feed", []):
                post = item.get("post", {})
                uri = post.get("uri", "")
                # Convert AT URI to web URL
                # at://did:plc:xxx/app.bsky.feed.post/yyy -> https://bsky.app/profile/handle/post/yyy
                post_id = uri.split("/")[-1] if uri else ""
                author_handle = post.get("author", {}).get("handle", self.handle)
                url = f"https://bsky.app/profile/{author_handle}/post/{post_id}" if post_id else ""
                results.append({
                    "id": uri,
                    "title": post.get("record", {}).get("text", "")[:50],
                    "published": True,
                    "url": url,
                })
            return results
        return []

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        """Get a specific post by AT URI."""
        return None  # TODO: implement

    def delete(self, article_id: str) -> bool:
        """Delete a post."""
        if not self._create_session():
            return False

        # article_id should be AT URI: at://did:plc:xxx/app.bsky.feed.post/yyy
        parts = article_id.replace("at://", "").split("/")
        if len(parts) < 3:
            return False

        rkey = parts[-1]

        resp = requests.post(
            f"{self.base_url}/com.atproto.repo.deleteRecord",
            headers=self._get_headers(),
            json={
                "repo": self.did,
                "collection": "app.bsky.feed.post",
                "rkey": rkey,
            },
        )

        return resp.status_code == 200
