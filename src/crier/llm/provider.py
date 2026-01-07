"""Base LLM provider interface for crier."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RewriteResult:
    """Result from an LLM rewrite operation."""

    text: str
    model: str
    tokens_used: int | None = None
    was_truncated: bool = False  # True if post-processing truncated the output
    original_length: int | None = None  # Original length before truncation


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
        *,
        previous_attempt: str | None = None,
        previous_length: int | None = None,
    ) -> RewriteResult:
        """Generate a short-form rewrite of article content.

        Args:
            title: Article title.
            body: Full article body text.
            max_chars: Maximum characters allowed for the output.
            platform: Target platform name (e.g., 'bluesky', 'mastodon').
            previous_attempt: Previous attempt text (for retry feedback).
            previous_length: Length of previous attempt (for retry feedback).

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
Write a short social media post announcing this blog article.

Rules:
- Maximum {max_chars} characters (HARD LIMIT - count carefully)
- Single paragraph, no line breaks
- Lead with the key insight or what makes this interesting
- Do NOT include any URL (one will be appended automatically)
- Do NOT include hashtags (they will be added from article tags)
- Sound like a real person sharing something interesting, not marketing copy
- Platform: {platform}

Title: {title}

Content:
{body}

Output only the post text, nothing else.
"""

# Retry prompt addition when previous attempt was too long
RETRY_PROMPT_ADDITION = """

IMPORTANT: Your previous attempt was {previous_length} characters, which exceeds the {max_chars} character limit by {excess} characters.
You MUST be more concise. Focus on the single most compelling point. Cut unnecessary words.
"""
