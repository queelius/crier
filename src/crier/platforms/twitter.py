"""Twitter/X platform implementation.

NOTE: Twitter API v2 requires OAuth 2.0 with PKCE for user context,
which is complex for a CLI tool. This implementation uses the simpler
OAuth 1.0a approach with API keys (requires Elevated access).

For most users, consider using Bluesky or Mastodon instead.
"""

from typing import Any

import requests
from requests_oauthlib import OAuth1

from .base import Article, Platform, PublishResult


class Twitter(Platform):
    """Twitter/X publishing platform.

    Requires Twitter Developer account with Elevated access.
    api_key format: "consumer_key:consumer_secret:access_token:access_token_secret"
    """

    name = "twitter"
    base_url = "https://api.twitter.com/2"

    def __init__(self, api_key: str):
        """Initialize with OAuth credentials.

        api_key should contain all four OAuth 1.0a credentials separated by colons.
        """
        super().__init__(api_key)

        parts = api_key.split(":")
        if len(parts) != 4:
            raise ValueError(
                "Twitter api_key must be: consumer_key:consumer_secret:access_token:access_token_secret"
            )

        self.consumer_key = parts[0]
        self.consumer_secret = parts[1]
        self.access_token = parts[2]
        self.access_token_secret = parts[3]

        self.auth = OAuth1(
            self.consumer_key,
            client_secret=self.consumer_secret,
            resource_owner_key=self.access_token,
            resource_owner_secret=self.access_token_secret,
        )

    def publish(self, article: Article) -> PublishResult:
        """Post a tweet.

        Creates a tweet with the article title and canonical URL.
        """
        # Create tweet text: title + URL
        text_parts = [article.title]
        if article.canonical_url:
            text_parts.append(article.canonical_url)

        text = "\n\n".join(text_parts)

        # Twitter limit is 280 chars (URLs count as ~23 chars after shortening)
        if len(text) > 280:
            # Truncate title to fit
            max_title = 280 - len(article.canonical_url or "") - 10
            text = article.title[:max_title] + "...\n\n" + (article.canonical_url or "")

        resp = requests.post(
            f"{self.base_url}/tweets",
            auth=self.auth,
            json={"text": text},
        )

        if resp.status_code in (200, 201):
            data = resp.json().get("data", {})
            tweet_id = data.get("id")
            # Construct URL (we'd need the username for full URL)
            url = f"https://twitter.com/i/status/{tweet_id}" if tweet_id else None

            return PublishResult(
                success=True,
                platform=self.name,
                article_id=tweet_id,
                url=url,
            )
        else:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"{resp.status_code}: {resp.text}",
            )

    def update(self, article_id: str, article: Article) -> PublishResult:
        """Twitter doesn't support editing tweets (for most accounts)."""
        return PublishResult(
            success=False,
            platform=self.name,
            error="Twitter does not support editing tweets",
        )

    def list_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        """List recent tweets."""
        # Need user ID first
        resp = requests.get(
            f"{self.base_url}/users/me",
            auth=self.auth,
        )

        if resp.status_code != 200:
            return []

        user_id = resp.json().get("data", {}).get("id")

        # Get tweets
        resp = requests.get(
            f"{self.base_url}/users/{user_id}/tweets",
            auth=self.auth,
            params={"max_results": min(limit, 100)},
        )

        if resp.status_code == 200:
            return [
                {
                    "id": tweet.get("id"),
                    "title": tweet.get("text", "")[:50],
                    "published": True,
                    "url": f"https://twitter.com/i/status/{tweet.get('id')}",
                }
                for tweet in resp.json().get("data", [])
            ]
        return []

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        """Get a specific tweet by ID."""
        resp = requests.get(
            f"{self.base_url}/tweets/{article_id}",
            auth=self.auth,
        )

        if resp.status_code == 200:
            return resp.json().get("data")
        return None

    def delete(self, article_id: str) -> bool:
        """Delete a tweet."""
        resp = requests.delete(
            f"{self.base_url}/tweets/{article_id}",
            auth=self.auth,
        )
        return resp.status_code == 200
