"""LinkedIn platform implementation.

Supports both API mode and manual mode.

NOTE: LinkedIn API access requires a Company Page or approved Marketing Developer Platform access.
For most users, manual mode (--manual flag) is the easier option.
"""

from typing import Any

import requests

from .base import Article, DeleteResult, Platform, PublishResult


class LinkedIn(Platform):
    """LinkedIn publishing platform.

    API mode: Requires OAuth 2.0 access token with w_member_social scope.
    api_key format: "access_token" or "access_token:person_urn"

    Manual mode: Use --manual flag to generate content for copy-paste.
    """

    name = "linkedin"
    description = "Professional network"
    base_url = "https://api.linkedin.com/v2"
    compose_url = "https://www.linkedin.com/feed/?shareActive=true"
    max_content_length = 3000
    api_key_url = None  # Requires OAuth app setup

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

    def format_for_manual(self, article: Article) -> str:
        """Format article for manual posting to LinkedIn.

        LinkedIn posts work best with a short intro, hashtags, and a link.
        """
        parts = [article.title]

        if article.description:
            parts.append(article.description)

        if article.tags:
            hashtags = " ".join(f"#{tag.replace('-', '')}" for tag in article.tags[:5])
            parts.append(hashtags)

        if article.canonical_url:
            parts.append(article.canonical_url)

        return "\n\n".join(parts)

    def _get_person_urn(self) -> str | None:
        """Get the authenticated user's URN."""
        if self.person_urn:
            return self.person_urn

        resp = requests.get(
            f"{self.base_url}/userinfo",
            headers=self.headers,
            timeout=30,
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

        # Check content length
        error = self._check_content_length(text)
        if error:
            return PublishResult(
                success=False,
                platform=self.name,
                error=error,
            )

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
            timeout=30,
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
            timeout=30,
        )

        if resp.status_code == 200:
            return resp.json()
        return None

    def delete(self, article_id: str) -> DeleteResult:
        """Delete a post."""
        resp = requests.delete(
            f"{self.base_url}/ugcPosts/{article_id}",
            headers=self.headers,
            timeout=30,
        )
        if resp.status_code == 204:
            return DeleteResult(success=True, platform=self.name)
        return DeleteResult(
            success=False,
            platform=self.name,
            error=f"{resp.status_code}: {resp.text}",
        )
