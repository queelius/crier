"""Threads (Meta) platform implementation."""

import time
from typing import Any

from .base import (
    Article,
    ArticleStats,
    DeleteResult,
    Platform,
    PublishResult,
    ThreadPublishResult,
)


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
    supports_threads = True
    thread_max_posts = 10

    def __init__(self, api_key: str):
        super().__init__(api_key)
        parts = api_key.split(":", 1)
        if len(parts) != 2:
            raise ValueError("Threads API key format: user_id:access_token")
        self.user_id = parts[0]
        self.access_token = parts[1]
        self._username: str | None = None

    def _get_username(self) -> str | None:
        """Fetch the Threads username for URL construction."""
        if self._username is not None:
            return self._username

        resp = self.retry_request(
            "get",
            f"{self.base_url}/{self.user_id}",
            params={"fields": "username", "access_token": self.access_token},
        )
        if resp.status_code == 200:
            self._username = resp.json().get("username")
        return self._username

    def _build_post_url(self, post_id: str) -> str | None:
        """Build a Threads post URL from post ID."""
        username = self._get_username()
        if username:
            return f"https://www.threads.net/@{username}/post/{post_id}"
        return None

    def _poll_container(self, creation_id: str) -> PublishResult | None:
        """Poll container status until ready. Returns error PublishResult or None on success."""
        for _ in range(10):
            time.sleep(1)
            status_resp = self.retry_request(
                "get",
                f"{self.base_url}/{creation_id}",
                params={
                    "fields": "status,error_message",
                    "access_token": self.access_token,
                },
            )
            if status_resp.status_code == 200:
                status_data = status_resp.json()
                container_status = status_data.get("status")
                if container_status == "FINISHED":
                    return None  # Success
                if container_status == "ERROR":
                    error_msg = status_data.get("error_message", "Unknown error")
                    return PublishResult(
                        success=False,
                        platform=self.name,
                        error=f"Container error: {error_msg}",
                    )
        return PublishResult(
            success=False,
            platform=self.name,
            error="Container polling timed out",
        )

    def _create_and_publish(
        self,
        text: str,
        reply_to_id: str | None = None,
    ) -> PublishResult:
        """Create container, poll, and publish. Shared by publish() and publish_thread()."""
        # Step 1: Create media container
        create_params: dict[str, Any] = {
            "media_type": "TEXT",
            "text": text,
            "access_token": self.access_token,
        }
        if reply_to_id:
            create_params["reply_to_id"] = reply_to_id

        resp = self.retry_request(
            "post",
            f"{self.base_url}/{self.user_id}/threads",
            params=create_params,
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

        # Step 2: Poll container status
        poll_error = self._poll_container(creation_id)
        if poll_error:
            return poll_error

        # Step 3: Publish the container
        publish_params = {
            "creation_id": creation_id,
            "access_token": self.access_token,
        }

        resp = self.retry_request(
            "post",
            f"{self.base_url}/{self.user_id}/threads_publish",
            params=publish_params,
        )

        if resp.status_code == 200:
            result = resp.json()
            post_id = result.get("id")
            url = self._build_post_url(post_id) if post_id else None
            return PublishResult(
                success=True,
                platform=self.name,
                article_id=post_id,
                url=url,
            )
        else:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"Publish failed: {resp.status_code}: {resp.text}",
            )

    def _format_post(self, article: Article) -> str:
        """Format article for Threads."""
        parts = [article.title]

        if article.description:
            parts.append(f"\n\n{article.description}")

        if article.canonical_url:
            parts.append(f"\n\n{article.canonical_url}")

        if article.tags:
            hashtags = " ".join(f"#{tag.replace('-', '_')}" for tag in article.tags[:3])
            parts.append(f"\n\n{hashtags}")

        return "".join(parts)

    def publish(self, article: Article) -> PublishResult:
        """Publish a post to Threads (two-step container process)."""
        text = self._format_post(article)

        if error := self._check_content_length(text):
            return PublishResult(
                success=False,
                platform=self.name,
                error=error,
            )

        return self._create_and_publish(text)

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

        resp = self.retry_request(
            "get",
            f"{self.base_url}/{self.user_id}/threads",
            params=params,
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

        resp = self.retry_request(
            "get",
            f"{self.base_url}/{article_id}",
            params=params,
        )

        if resp.status_code == 200:
            return resp.json()
        return None

    def get_stats(self, article_id: str) -> ArticleStats | None:
        """Get engagement stats for a Threads post.

        Uses the Threads Insights API to fetch likes, replies, and reposts.
        """
        resp = self.retry_request(
            "get",
            f"{self.base_url}/{article_id}/insights",
            params={
                "metric": "likes,replies,reposts,views",
                "access_token": self.access_token,
            },
        )

        if resp.status_code != 200:
            return None

        data = resp.json().get("data", [])
        stats: dict[str, int] = {}
        for metric in data:
            name = metric.get("name")
            values = metric.get("values", [{}])
            value = values[0].get("value", 0) if values else 0
            stats[name] = value

        return ArticleStats(
            views=stats.get("views"),
            likes=stats.get("likes"),
            comments=stats.get("replies"),
            reposts=stats.get("reposts"),
        )

    def publish_thread(self, posts: list[str]) -> ThreadPublishResult:
        """Publish a thread of posts to Threads.

        Each post is published as a reply to the previous one.

        Args:
            posts: List of post content strings

        Returns:
            ThreadPublishResult with all post IDs and URLs
        """
        results = []
        post_ids = []
        post_urls = []
        reply_to_id = None

        for i, post_text in enumerate(posts):
            if len(post_text) > self.max_content_length:
                return ThreadPublishResult(
                    success=False,
                    platform=self.name,
                    error=(
                        f"Post {i + 1} exceeds character limit"
                        f" ({len(post_text)} > {self.max_content_length})"
                    ),
                    results=results,
                )

            result = self._create_and_publish(post_text, reply_to_id=reply_to_id)
            results.append(result)

            if result.success:
                reply_to_id = result.article_id
                post_ids.append(result.article_id)
                post_urls.append(result.url)
            else:
                return ThreadPublishResult(
                    success=False,
                    platform=self.name,
                    error=f"Thread post {i + 1} failed: {result.error}",
                    results=results,
                    post_ids=post_ids,
                    post_urls=post_urls,
                )

        return ThreadPublishResult(
            success=True,
            platform=self.name,
            root_id=post_ids[0] if post_ids else None,
            root_url=post_urls[0] if post_urls else None,
            post_ids=post_ids,
            post_urls=post_urls,
            results=results,
        )

    def delete(self, article_id: str) -> DeleteResult:
        """Threads API doesn't support deleting posts via API."""
        return DeleteResult(
            success=False,
            platform=self.name,
            error="Threads API does not support deleting posts. Delete manually at threads.net",
        )
