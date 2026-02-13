"""Mastodon platform implementation."""

from typing import Any

from .base import Article, ArticleStats, DeleteResult, Platform, PublishResult, ThreadPublishResult


class Mastodon(Platform):
    """Mastodon publishing platform.

    Requires instance URL and access token.
    api_key format: "instance_url:access_token" (e.g., "mastodon.social:token123")
    """

    name = "mastodon"
    description = "Short posts (500 chars)"
    max_content_length = 500  # Default Mastodon limit (some instances allow more)
    api_key_url = None  # Instance-specific
    supports_threads = True
    supports_stats = True

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

        resp = self.retry_request(
            "post",
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

        resp = self.retry_request(
            "put",
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
        resp = self.retry_request(
            "get",
            f"{self.instance}/api/v1/accounts/verify_credentials",
            headers=self.headers,
        )

        if resp.status_code != 200:
            return []

        account_id = resp.json().get("id")

        # Then get statuses
        resp = self.retry_request(
            "get",
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
        resp = self.retry_request(
            "get",
            f"{self.instance}/api/v1/statuses/{article_id}",
            headers=self.headers,
        )

        if resp.status_code == 200:
            return resp.json()
        return None

    def delete(self, article_id: str) -> DeleteResult:
        """Delete a toot."""
        resp = self.retry_request(
            "delete",
            f"{self.instance}/api/v1/statuses/{article_id}",
            headers=self.headers,
        )
        if resp.status_code == 200:
            return DeleteResult(success=True, platform=self.name)
        return DeleteResult(
            success=False,
            platform=self.name,
            error=f"{resp.status_code}: {resp.text}",
        )

    def get_stats(self, article_id: str) -> ArticleStats | None:
        """Get engagement stats for a toot.

        Mastodon provides favourites (likes), replies, and reblogs (reposts).
        Views are not available via the API.
        """
        status = self.get_article(article_id)
        if not status:
            return None

        return ArticleStats(
            likes=status.get("favourites_count"),
            comments=status.get("replies_count"),
            reposts=status.get("reblogs_count"),
        )

    def publish_thread(self, posts: list[str]) -> ThreadPublishResult:
        """Publish a thread of toots to Mastodon.

        Each post is published as a reply to the previous one,
        creating a connected thread.

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
            # Check content length
            if len(post_text) > self.max_content_length:
                return ThreadPublishResult(
                    success=False,
                    platform=self.name,
                    error=f"Post {i + 1} exceeds character limit ({len(post_text)} > {self.max_content_length})",
                    results=results,
                )

            data = {
                "status": post_text,
                "visibility": "public",
            }

            # Add reply reference if not the first post
            if reply_to_id:
                data["in_reply_to_id"] = reply_to_id

            resp = self.retry_request(
                "post",
                f"{self.instance}/api/v1/statuses",
                headers=self.headers,
                json=data,
            )

            if resp.status_code in (200, 201):
                result = resp.json()
                status_id = str(result.get("id"))
                url = result.get("url")

                reply_to_id = status_id
                post_ids.append(status_id)
                post_urls.append(url)

                results.append(PublishResult(
                    success=True,
                    platform=self.name,
                    article_id=status_id,
                    url=url,
                ))
            else:
                # Failed to post - return partial results
                results.append(PublishResult(
                    success=False,
                    platform=self.name,
                    error=f"{resp.status_code}: {resp.text}",
                ))
                return ThreadPublishResult(
                    success=False,
                    platform=self.name,
                    error=f"Failed on post {i + 1}: {resp.status_code}: {resp.text}",
                    root_id=post_ids[0] if post_ids else None,
                    root_url=post_urls[0] if post_urls else None,
                    post_ids=post_ids,
                    post_urls=post_urls,
                    results=results,
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
