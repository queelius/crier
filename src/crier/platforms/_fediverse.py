"""Fediverse base: Mastodon-API-compatible servers.

The fediverse runs many server implementations (Mastodon, Pleroma, Akkoma,
GoToSocial, Misskey forks with mastoapi enabled, Pixelfed, Friendica) that
all converge on the same client-to-server REST API. ActivityPub itself is
the server-to-server federation protocol. For posting content from a
client, which is what crier does, the de facto standard is Mastodon's REST
API at ``/api/v1/statuses``.

This base class implements that API. Server-specific subclasses override
class attributes (``name``, ``description``, ``max_content_length``,
``default_instance``) but inherit all request logic.

The leading underscore on the module name keeps this file out of the
package's platform auto-discovery (see ``platforms/__init__.py``), so
``FediversePlatform`` is not itself registered as a user-visible platform.
Only its concrete subclasses (Mastodon, Pleroma, ...) get registered.

Servers that do NOT implement Mastodon's API (Lemmy, PeerTube) need their
own platform classes and do not derive from this base.
"""

from __future__ import annotations

import re
from typing import Any

from .base import (
    Article,
    ArticleStats,
    DeleteResult,
    Platform,
    PublishResult,
    ThreadPublishResult,
)


class FediversePlatform(Platform):
    """Base class for Mastodon-API-compatible fediverse servers.

    Subclasses set the following class attributes:

    - ``name``: platform identifier (e.g. ``"mastodon"``, ``"pleroma"``)
    - ``description``: short human-readable description
    - ``max_content_length``: character limit advertised by the platform
      (Mastodon defaults to 500; Pleroma 5000; some operators raise either)
    - ``default_instance``: hostname of the default instance, or ``None``
      if every user must configure their own (Pleroma, Akkoma)

    Construction accepts the same ``api_key`` shape as the original Mastodon
    platform: either ``"instance.host:token"`` or just ``"token"`` paired
    with an explicit ``instance`` argument.
    """

    is_short_form: bool = True
    supports_threads: bool = True
    supports_stats: bool = True
    api_key_url: str | None = None  # Instance-specific; subclasses may override

    # Subclasses override; None means user MUST supply an instance via
    # the ``instance:token`` api_key shape or the ``instance`` argument.
    default_instance: str | None = None

    def __init__(self, api_key: str, instance: str | None = None):
        super().__init__(api_key)

        if ":" in api_key and instance is None:
            # api_key may already include a scheme ("http://localhost:3000:tok"
            # is legitimate for self-hosted dev instances). When it does, the
            # token separator is the LAST colon; otherwise the FIRST colon
            # separates a bare host from its token.
            if api_key.startswith(("http://", "https://")):
                self.instance, self.access_token = api_key.rsplit(":", 1)
            else:
                self.instance, self.access_token = api_key.split(":", 1)
        else:
            self.instance = instance or self.default_instance
            self.access_token = api_key

        if not self.instance:
            raise ValueError(
                f"{type(self).__name__} requires an instance hostname. "
                f"Pass api_key as 'instance.example.org:token' or set the "
                f"instance argument explicitly."
            )

        # Normalize instance URL
        if not self.instance.startswith("http"):
            self.instance = f"https://{self.instance}"

        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    # --- post composition helpers ---------------------------------------

    def _compose_text(self, article: Article, *, include_hashtags: bool = True) -> str:
        """Build the post text from an Article.

        ``include_hashtags`` is true for new posts and false for edits, so
        that updating a status doesn't append a hashtag block.
        """
        if article.is_rewrite:
            return self._append_canonical_url(article.body, article)

        text_parts = [article.title]
        if article.description:
            text_parts.append(article.description)
        if article.canonical_url:
            text_parts.append(article.canonical_url)
        if include_hashtags and article.tags:
            hashtags = " ".join(f"#{tag.replace('-', '')}" for tag in article.tags[:5])
            text_parts.append(hashtags)
        return "\n\n".join(text_parts)

    def _publish_result(self, resp: Any, ok_codes: tuple[int, ...]) -> PublishResult:
        """Convert a status response into a PublishResult.

        When the response indicates success, ``article_id`` is set from the
        body's ``id`` field; if the field is missing, it stays ``None``
        rather than the literal string ``"None"``, so the registry doesn't
        accumulate garbage IDs from misbehaving servers.
        """
        if resp.status_code in ok_codes:
            result = resp.json()
            raw_id = result.get("id")
            return PublishResult(
                success=True,
                platform=self.name,
                article_id=str(raw_id) if raw_id is not None else None,
                url=result.get("url"),
            )
        return PublishResult(
            success=False,
            platform=self.name,
            error=f"{resp.status_code}: {resp.text}",
        )

    @staticmethod
    def _strip_html(content_html: str) -> str:
        """Convert Mastodon HTML-flavored content to plain text.

        Replaces ``</p><p>`` and ``<br>`` with newlines, strips remaining
        tags, and collapses runs of inline whitespace without merging
        intentional newlines.
        """
        text = re.sub(r"</p>\s*<p[^>]*>", "\n", content_html)
        text = re.sub(r"<br\s*/?>", "\n", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"[^\S\n]+", " ", text)
        return text.strip()

    # --- Platform interface --------------------------------------------

    def publish(self, article: Article) -> PublishResult:
        """Post a status. Uses ``article.body`` if ``is_rewrite``, else builds
        from title/description/url/tags.
        """
        text = self._compose_text(article)

        if error := self._check_content_length(text):
            return PublishResult(success=False, platform=self.name, error=error)

        resp = self.retry_request(
            "post",
            f"{self.instance}/api/v1/statuses",
            headers=self.headers,
            json={
                "status": text,
                "visibility": "public" if article.published else "private",
            },
        )
        return self._publish_result(resp, ok_codes=(200, 201))

    def update(self, article_id: str, article: Article) -> PublishResult:
        """Edit an existing status (Mastodon-API supports edits)."""
        text = self._compose_text(article, include_hashtags=False)

        if error := self._check_content_length(text):
            return PublishResult(success=False, platform=self.name, error=error)

        resp = self.retry_request(
            "put",
            f"{self.instance}/api/v1/statuses/{article_id}",
            headers=self.headers,
            json={"status": text},
        )
        return self._publish_result(resp, ok_codes=(200,))

    def list_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        """List your recent statuses."""
        resp = self.retry_request(
            "get",
            f"{self.instance}/api/v1/accounts/verify_credentials",
            headers=self.headers,
        )
        if resp.status_code != 200:
            return []

        account_id = resp.json().get("id")

        resp = self.retry_request(
            "get",
            f"{self.instance}/api/v1/accounts/{account_id}/statuses",
            headers=self.headers,
            params={"limit": limit},
        )
        if resp.status_code != 200:
            return []

        results = []
        for status in resp.json():
            text = self._strip_html(status.get("content", ""))
            first_line = text.split("\n")[0].strip()
            title = first_line[:100] if first_line else text[:100]
            results.append(
                {
                    "id": status.get("id"),
                    "title": title,
                    "content": text,
                    "published": status.get("visibility") == "public",
                    "url": status.get("url"),
                }
            )
        return results

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        """Get a specific status by ID."""
        resp = self.retry_request(
            "get",
            f"{self.instance}/api/v1/statuses/{article_id}",
            headers=self.headers,
        )
        if resp.status_code == 200:
            return resp.json()
        return None

    def delete(self, article_id: str) -> DeleteResult:
        """Delete a status."""
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
        """Engagement stats: favourites, replies, reblogs.

        Views are not exposed by the Mastodon API.
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
        """Publish posts as a connected thread.

        Each post replies to the previous via ``in_reply_to_id``.
        """
        results: list[PublishResult] = []
        post_ids: list[str] = []
        post_urls: list[str] = []
        reply_to_id: str | None = None

        def thread_result(success: bool, error: str | None = None) -> ThreadPublishResult:
            return ThreadPublishResult(
                success=success,
                platform=self.name,
                error=error,
                root_id=post_ids[0] if post_ids else None,
                root_url=post_urls[0] if post_urls else None,
                post_ids=post_ids,
                post_urls=post_urls,
                results=results,
            )

        for i, post_text in enumerate(posts):
            if len(post_text) > self.max_content_length:
                return thread_result(
                    success=False,
                    error=(
                        f"Post {i + 1} exceeds character limit "
                        f"({len(post_text)} > {self.max_content_length})"
                    ),
                )

            data: dict[str, Any] = {"status": post_text, "visibility": "public"}
            if reply_to_id:
                data["in_reply_to_id"] = reply_to_id

            resp = self.retry_request(
                "post",
                f"{self.instance}/api/v1/statuses",
                headers=self.headers,
                json=data,
            )
            post_result = self._publish_result(resp, ok_codes=(200, 201))
            results.append(post_result)

            if not post_result.success:
                return thread_result(
                    success=False,
                    error=f"Failed on post {i + 1}: {resp.status_code}: {resp.text}",
                )

            reply_to_id = post_result.article_id
            post_ids.append(post_result.article_id)
            post_urls.append(post_result.url)

        return thread_result(success=True)
