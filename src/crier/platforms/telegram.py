"""Telegram channel platform implementation."""

from typing import Any

import requests

from .base import Article, Platform, PublishResult


class Telegram(Platform):
    """Telegram channel/group publishing via Bot API.

    API key format: bot_token:chat_id
    - bot_token: Get from @BotFather
    - chat_id: Channel username (@channelname) or numeric chat ID

    The bot must be an admin of the channel with posting permissions.
    """

    name = "telegram"

    def __init__(self, api_key: str):
        super().__init__(api_key)
        parts = api_key.split(":", 1)
        if len(parts) != 2:
            raise ValueError("Telegram API key format: bot_token:chat_id")

        # Bot token contains a colon (123456:ABC-DEF...), so we need to be careful
        # Actually the format is: full_bot_token:chat_id where bot_token itself has colon
        # Let's use a different delimiter or expect: bottoken:chatid
        # Better: split from the right on last colon
        parts = api_key.rsplit(":", 1)
        self.bot_token = parts[0]
        self.chat_id = parts[1]
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def _format_message(self, article: Article) -> str:
        """Format article as Telegram message with markdown."""
        parts = [f"*{article.title}*"]

        if article.description:
            parts.append(f"\n{article.description}")

        if article.canonical_url:
            parts.append(f"\n\n🔗 {article.canonical_url}")

        if article.tags:
            hashtags = " ".join(f"#{tag.replace('-', '_')}" for tag in article.tags[:5])
            parts.append(f"\n\n{hashtags}")

        return "".join(parts)

    def publish(self, article: Article) -> PublishResult:
        """Send a message to Telegram channel."""
        message = self._format_message(article)

        data = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,  # Enable link previews
        }

        resp = requests.post(
            f"{self.base_url}/sendMessage",
            json=data,
        )

        if resp.status_code == 200:
            result = resp.json()
            if result.get("ok"):
                msg = result.get("result", {})
                message_id = msg.get("message_id")
                # Telegram messages don't have public URLs unless it's a public channel
                chat = msg.get("chat", {})
                username = chat.get("username")
                url = f"https://t.me/{username}/{message_id}" if username else None
                return PublishResult(
                    success=True,
                    platform=self.name,
                    article_id=str(message_id),
                    url=url,
                )
            else:
                return PublishResult(
                    success=False,
                    platform=self.name,
                    error=result.get("description", "Unknown error"),
                )
        else:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"{resp.status_code}: {resp.text}",
            )

    def update(self, article_id: str, article: Article) -> PublishResult:
        """Edit a message in Telegram channel."""
        message = self._format_message(article)

        data = {
            "chat_id": self.chat_id,
            "message_id": int(article_id),
            "text": message,
            "parse_mode": "Markdown",
        }

        resp = requests.post(
            f"{self.base_url}/editMessageText",
            json=data,
        )

        if resp.status_code == 200:
            result = resp.json()
            if result.get("ok"):
                msg = result.get("result", {})
                chat = msg.get("chat", {})
                username = chat.get("username")
                url = f"https://t.me/{username}/{article_id}" if username else None
                return PublishResult(
                    success=True,
                    platform=self.name,
                    article_id=article_id,
                    url=url,
                )
            else:
                return PublishResult(
                    success=False,
                    platform=self.name,
                    error=result.get("description", "Unknown error"),
                )
        else:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"{resp.status_code}: {resp.text}",
            )

    def list_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        """Telegram Bot API doesn't support listing channel messages.

        This would require storing message IDs locally or using Telegram's
        MTProto API with user authentication.
        """
        return []

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        """Telegram Bot API doesn't support fetching specific messages."""
        return None

    def delete(self, article_id: str) -> bool:
        """Delete a message from Telegram channel."""
        data = {
            "chat_id": self.chat_id,
            "message_id": int(article_id),
        }

        resp = requests.post(
            f"{self.base_url}/deleteMessage",
            json=data,
        )

        if resp.status_code == 200:
            result = resp.json()
            return result.get("ok", False)
        return False
