"""LinkedIn platform implementation.

NOTE: LinkedIn API access requires a Company Page or approved Marketing Developer Platform access.
This is more complex than other platforms. For most users, sharing via web interface is easier.

This implementation provides a basic structure but may need adjustments based on your
specific LinkedIn API access level.
"""

from typing import Any

import requests

from .base import Article, Platform, PublishResult


class LinkedIn(Platform):
    """LinkedIn publishing platform.

    Requires OAuth 2.0 access token with w_member_social scope.
    api_key format: "access_token" or "access_token:person_urn"
    """

    name = "linkedin"
    base_url = "https://api.linkedin.com/v2"

    def __init__(self, api_key: str, person_urn: str | None = None):
        super().__init__(api_key)

        if ":" in api_key and person_urn is None:
            self.access_token, self.person_urn = api_key.split(":", 1)
        else:
            self.access_token = api_key
            self.person_urn = person_urn

        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

    def _get_person_urn(self) -> str | None:
        """Get the authenticated user's URN."""
        if self.person_urn:
            return self.person_urn

        resp = requests.get(
            f"{self.base_url}/userinfo",
            headers=self.headers,
        )

        if resp.status_code == 200:
            user_id = resp.json().get("sub")
            if user_id:
                self.person_urn = f"urn:li:person:{user_id}"
                return self.person_urn
        return None

    def publish(self, article: Article) -> PublishResult:
        """Create a LinkedIn post with link.

        Note: Full article publishing requires LinkedIn Publishing Platform access.
        This creates a share/post with link preview.
        """
        person_urn = self._get_person_urn()
        if not person_urn:
            return PublishResult(
                success=False,
                platform=self.name,
                error="Failed to get LinkedIn profile. Check your access token.",
            )

        # Create post text
        text_parts = [article.title]
        if article.description:
            text_parts.append(article.description)

        # Add hashtags from tags
        if article.tags:
            hashtags = " ".join(f"#{tag.replace('-', '')}" for tag in article.tags[:5])
            text_parts.append(hashtags)

        text = "\n\n".join(text_parts)

        # LinkedIn post limit is 3000 chars
        if len(text) > 3000:
            text = text[:2997] + "..."

        # Create share with article link
        data = {
            "author": person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "ARTICLE" if article.canonical_url else "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }

        if article.canonical_url:
            data["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [
                {
                    "status": "READY",
                    "originalUrl": article.canonical_url,
                }
            ]

        resp = requests.post(
            f"{self.base_url}/ugcPosts",
            headers=self.headers,
            json=data,
        )

        if resp.status_code in (200, 201):
            post_id = resp.headers.get("x-restli-id", "")
            # LinkedIn post URLs are complex; this is a simplified version
            return PublishResult(
                success=True,
                platform=self.name,
                article_id=post_id,
                url=f"https://www.linkedin.com/feed/update/{post_id}",
            )
        else:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"{resp.status_code}: {resp.text}",
            )

    def update(self, article_id: str, article: Article) -> PublishResult:
        """LinkedIn doesn't support editing posts via API."""
        return PublishResult(
            success=False,
            platform=self.name,
            error="LinkedIn API does not support editing posts",
        )

    def list_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        """List recent posts is limited in LinkedIn API."""
        return []

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        """Get a specific post."""
        resp = requests.get(
            f"{self.base_url}/ugcPosts/{article_id}",
            headers=self.headers,
        )

        if resp.status_code == 200:
            return resp.json()
        return None

    def delete(self, article_id: str) -> bool:
        """Delete a post."""
        resp = requests.delete(
            f"{self.base_url}/ugcPosts/{article_id}",
            headers=self.headers,
        )
        return resp.status_code == 204
