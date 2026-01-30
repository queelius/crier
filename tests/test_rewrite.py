"""Tests for crier.rewrite — auto-rewrite logic."""

from unittest.mock import MagicMock, patch

import pytest

from crier.platforms.base import Article
from crier.rewrite import AutoRewriteResult, auto_rewrite_for_platform


@pytest.fixture
def long_article():
    """Article with body exceeding typical platform limits."""
    return Article(
        title="Test Article",
        body="x" * 500,
        description="A test article",
        tags=["test"],
        canonical_url="https://example.com/test",
        published=True,
    )


@pytest.fixture
def mock_provider():
    """Mock LLM provider."""
    provider = MagicMock()
    provider.model = "test-model"
    return provider


def _make_rewrite_result(text, was_truncated=False):
    """Create a mock RewriteResult."""
    result = MagicMock()
    result.text = text
    result.was_truncated = was_truncated
    result.model = "test-model"
    result.tokens_used = 100
    return result


class TestAutoRewriteForPlatform:
    """Tests for auto_rewrite_for_platform()."""

    def test_success_first_attempt(self, long_article, mock_provider):
        """Rewrite fits on first try."""
        mock_provider.rewrite.return_value = _make_rewrite_result(
            "Short rewrite"
        )

        result = auto_rewrite_for_platform(
            long_article, "bluesky", 300, mock_provider, silent=True,
        )

        assert result.success is True
        assert result.article is not None
        assert result.article.body == "Short rewrite"
        assert result.article.title == "Test Article"
        assert result.rewrite_text == "Short rewrite"
        assert result.error is None
        mock_provider.rewrite.assert_called_once()

    def test_success_after_retry(self, long_article, mock_provider):
        """Rewrite succeeds after a retry."""
        # First attempt too long, second fits
        mock_provider.rewrite.side_effect = [
            _make_rewrite_result("x" * 400),  # too long
            _make_rewrite_result("Short enough"),  # fits
        ]

        result = auto_rewrite_for_platform(
            long_article, "bluesky", 300, mock_provider,
            retry_count=1, silent=True,
        )

        assert result.success is True
        assert result.article.body == "Short enough"
        assert mock_provider.rewrite.call_count == 2

    def test_truncation_fallback(self, long_article, mock_provider):
        """Falls back to truncation when retries exhausted."""
        mock_provider.rewrite.return_value = _make_rewrite_result(
            "First sentence. Second sentence. Third sentence is too long."
        )

        result = auto_rewrite_for_platform(
            long_article, "bluesky", 40, mock_provider,
            retry_count=0, truncate_fallback=True, silent=True,
        )

        assert result.success is True
        assert result.article is not None
        assert len(result.rewrite_text) <= 40

    def test_failure_too_long_no_truncate(self, long_article, mock_provider):
        """Fails when too long and truncation not enabled."""
        mock_provider.rewrite.return_value = _make_rewrite_result(
            "x" * 400
        )

        result = auto_rewrite_for_platform(
            long_article, "bluesky", 300, mock_provider,
            retry_count=0, truncate_fallback=False, silent=True,
        )

        assert result.success is False
        assert "too long" in result.error
        assert result.article is None

    def test_failure_llm_error(self, long_article, mock_provider):
        """Handles LLM provider errors gracefully."""
        from crier.llm import LLMProviderError

        mock_provider.rewrite.side_effect = LLMProviderError("API down")

        result = auto_rewrite_for_platform(
            long_article, "bluesky", 300, mock_provider, silent=True,
        )

        assert result.success is False
        assert "Auto-rewrite failed" in result.error
        assert "API down" in result.error

    def test_preserves_article_metadata(self, mock_provider):
        """Rewritten article preserves all metadata from original."""
        article = Article(
            title="My Title",
            body="x" * 500,
            description="My description",
            tags=["python", "testing"],
            canonical_url="https://example.com/my-post",
            published=True,
            cover_image="https://example.com/cover.jpg",
        )
        mock_provider.rewrite.return_value = _make_rewrite_result(
            "Short rewrite"
        )

        result = auto_rewrite_for_platform(
            article, "bluesky", 300, mock_provider, silent=True,
        )

        assert result.article.title == "My Title"
        assert result.article.description == "My description"
        assert result.article.tags == ["python", "testing"]
        assert result.article.canonical_url == "https://example.com/my-post"
        assert result.article.published is True
        assert result.article.cover_image == "https://example.com/cover.jpg"

    def test_console_output_when_not_silent(self, long_article, mock_provider):
        """Produces console output when not silent."""
        mock_provider.rewrite.return_value = _make_rewrite_result(
            "Short rewrite"
        )
        mock_console = MagicMock()

        result = auto_rewrite_for_platform(
            long_article, "bluesky", 300, mock_provider,
            silent=False, console=mock_console,
        )

        assert result.success is True
        assert mock_console.print.call_count >= 2  # progress + success

    def test_retry_with_previous_attempt(self, long_article, mock_provider):
        """Passes previous attempt info to LLM on retries."""
        mock_provider.rewrite.side_effect = [
            _make_rewrite_result("x" * 400),
            _make_rewrite_result("Short"),
        ]

        auto_rewrite_for_platform(
            long_article, "bluesky", 300, mock_provider,
            retry_count=1, silent=True,
        )

        # Second call should have previous attempt info
        second_call = mock_provider.rewrite.call_args_list[1]
        assert second_call.kwargs["previous_attempt"] == "x" * 400
        assert second_call.kwargs["previous_length"] == 400

    def test_multiple_retries_all_fail(self, long_article, mock_provider):
        """All retries fail, error includes attempt count."""
        mock_provider.rewrite.return_value = _make_rewrite_result(
            "x" * 400
        )

        result = auto_rewrite_for_platform(
            long_article, "bluesky", 300, mock_provider,
            retry_count=3, truncate_fallback=False, silent=True,
        )

        assert result.success is False
        assert "4 attempt(s)" in result.error  # 1 initial + 3 retries
        assert mock_provider.rewrite.call_count == 4

    def test_zero_retry_count(self, long_article, mock_provider):
        """With retry_count=0, only one attempt is made."""
        mock_provider.rewrite.return_value = _make_rewrite_result(
            "x" * 400
        )

        result = auto_rewrite_for_platform(
            long_article, "bluesky", 300, mock_provider,
            retry_count=0, silent=True,
        )

        assert result.success is False
        assert mock_provider.rewrite.call_count == 1


class TestAutoRewriteResult:
    """Tests for the AutoRewriteResult dataclass."""

    def test_success_result(self):
        article = Article(title="T", body="B")
        result = AutoRewriteResult(
            success=True, article=article, rewrite_text="B"
        )
        assert result.success is True
        assert result.error is None

    def test_failure_result(self):
        result = AutoRewriteResult(success=False, error="Something broke")
        assert result.success is False
        assert result.article is None
        assert result.rewrite_text is None
