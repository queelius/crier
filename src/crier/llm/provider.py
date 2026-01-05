"""Base LLM provider interface for crier."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RewriteResult:
    """Result from an LLM rewrite operation."""

    text: str
    model: str
    tokens_used: int | None = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Providers generate short-form rewrites of article content for
    platforms with character limits (Bluesky, Twitter, etc.).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'openai', 'ollama')."""
        ...

    @abstractmethod
    def rewrite(
        self,
        title: str,
        body: str,
        max_chars: int,
        platform: str,
    ) -> RewriteResult:
        """Generate a short-form rewrite of article content.

        Args:
            title: Article title.
            body: Full article body text.
            max_chars: Maximum characters allowed for the output.
            platform: Target platform name (e.g., 'bluesky', 'mastodon').

        Returns:
            RewriteResult with the generated text and metadata.

        Raises:
            LLMProviderError: If the rewrite fails.
        """
        ...


class LLMProviderError(Exception):
    """Error from LLM provider."""

    pass


# Default prompt template for rewrites
DEFAULT_REWRITE_PROMPT = """\
Write a short social media announcement for this article.

Requirements:
- Maximum {max_chars} characters (this is a hard limit)
- Platform: {platform}
- Capture the key insight or hook
- Do NOT include the URL (it will be appended automatically)
- Do NOT use hashtags (they will be added from article tags)
- Write in an engaging but not clickbait style

Article title: {title}

Article content:
{body}

Write ONLY the announcement text, nothing else.
"""
