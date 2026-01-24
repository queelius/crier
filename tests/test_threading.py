"""Tests for crier.threading module."""

import pytest
from datetime import datetime, timezone

from crier.threading import (
    split_into_thread,
    split_by_sentences,
    split_by_words,
    format_thread,
    estimate_thread_count,
)
from crier.registry import (
    record_thread_publication,
    is_thread,
    get_thread_ids,
    load_registry,
)


class TestSplitIntoThread:
    """Tests for split_into_thread function."""

    def test_short_content_single_post(self):
        """Short content stays as single post."""
        content = "This is a short post."
        posts = split_into_thread(content, max_length=280, style="simple")
        assert len(posts) == 1
        assert posts[0] == "This is a short post."

    def test_manual_markers(self):
        """Manual markers split content."""
        content = "First post.<!-- thread -->Second post.<!-- thread -->Third post."
        posts = split_into_thread(content, max_length=280, style="simple")
        assert len(posts) == 3
        assert posts[0] == "First post."
        assert posts[1] == "Second post."
        assert posts[2] == "Third post."

    def test_paragraph_splitting(self):
        """Content splits at paragraph boundaries."""
        content = "First paragraph with some text.\n\nSecond paragraph with more text."
        posts = split_into_thread(content, max_length=50, style="simple")
        assert len(posts) == 2

    def test_numbered_style(self):
        """Numbered style adds x/y prefix."""
        # Use max_length=40 to force split (content is 35 chars, effective limit 40-15=25)
        content = "First paragraph.\n\nSecond paragraph."
        posts = split_into_thread(content, max_length=40, style="numbered")
        assert len(posts) == 2
        assert posts[0].startswith("1/2")
        assert posts[1].startswith("2/2")

    def test_emoji_style(self):
        """Emoji style adds thread emoji prefix."""
        content = "First paragraph.\n\nSecond paragraph."
        posts = split_into_thread(content, max_length=40, style="emoji")
        assert len(posts) == 2
        assert "\U0001f9f5" in posts[0]  # Thread emoji

    def test_simple_style_no_prefix(self):
        """Simple style has no prefix."""
        content = "First paragraph.\n\nSecond paragraph."
        posts = split_into_thread(content, max_length=40, style="simple")
        assert len(posts) == 2
        assert not posts[0].startswith("1/2")
        assert "First paragraph" in posts[0]

    def test_max_posts_limit(self):
        """Thread is limited to max_posts."""
        # Create content that would split into 10 posts
        content = "\n\n".join([f"Paragraph {i}." for i in range(10)])
        posts = split_into_thread(content, max_length=30, style="simple", max_posts=5)
        assert len(posts) <= 5

    def test_long_paragraph_splits_by_sentence(self):
        """Long paragraphs split at sentence boundaries."""
        content = "This is sentence one. This is sentence two. This is sentence three. This is sentence four."
        posts = split_into_thread(content, max_length=60, style="simple")
        assert len(posts) >= 2


class TestSplitBySentences:
    """Tests for split_by_sentences function."""

    def test_basic_split(self):
        """Split at sentence boundaries."""
        text = "First sentence. Second sentence. Third sentence."
        chunks = split_by_sentences(text, max_length=30)
        assert len(chunks) >= 2

    def test_preserves_sentences(self):
        """Sentences stay together when possible."""
        text = "Short. Also short."
        chunks = split_by_sentences(text, max_length=50)
        assert len(chunks) == 1
        assert chunks[0] == "Short. Also short."


class TestSplitByWords:
    """Tests for split_by_words function."""

    def test_basic_split(self):
        """Split at word boundaries."""
        text = "word1 word2 word3 word4 word5"
        chunks = split_by_words(text, max_length=15)
        assert len(chunks) >= 2

    def test_oversized_word_truncated(self):
        """Oversized words are truncated."""
        text = "supercalifragilisticexpialidocious"
        chunks = split_by_words(text, max_length=20)
        assert len(chunks) == 1
        assert len(chunks[0]) <= 20


class TestFormatThread:
    """Tests for format_thread function."""

    def test_single_post_no_format(self):
        """Single post gets no thread indicator."""
        posts = ["Just one post."]
        formatted = format_thread(posts, style="numbered", max_length=280, max_posts=25)
        assert len(formatted) == 1
        assert formatted[0] == "Just one post."

    def test_numbered_format(self):
        """Numbered format adds position indicators."""
        posts = ["First", "Second", "Third"]
        formatted = format_thread(posts, style="numbered", max_length=280, max_posts=25)
        assert formatted[0].startswith("1/3")
        assert formatted[1].startswith("2/3")
        assert formatted[2].startswith("3/3")

    def test_emoji_format(self):
        """Emoji format adds thread emoji."""
        posts = ["First", "Second"]
        formatted = format_thread(posts, style="emoji", max_length=280, max_posts=25)
        assert "\U0001f9f5" in formatted[0]
        assert "1/2" in formatted[0]

    def test_simple_format(self):
        """Simple format has no indicators."""
        posts = ["First", "Second"]
        formatted = format_thread(posts, style="simple", max_length=280, max_posts=25)
        assert formatted[0] == "First"
        assert formatted[1] == "Second"

    def test_truncates_long_content(self):
        """Content that's too long with prefix gets truncated."""
        posts = ["A" * 300]  # Too long
        formatted = format_thread(posts, style="numbered", max_length=100, max_posts=25)
        assert len(formatted[0]) <= 100


class TestEstimateThreadCount:
    """Tests for estimate_thread_count function."""

    def test_short_content(self):
        """Short content estimates 1 post."""
        count = estimate_thread_count("Short post.", max_length=280)
        assert count == 1

    def test_long_content(self):
        """Long content estimates multiple posts."""
        content = "\n\n".join([f"Paragraph {i} with some content." for i in range(10)])
        count = estimate_thread_count(content, max_length=50)
        assert count > 1


@pytest.fixture
def tmp_registry(tmp_path, monkeypatch):
    """Set up a temporary registry directory."""
    crier_dir = tmp_path / ".crier"
    crier_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestRegistryThreadFunctions:
    """Tests for registry thread-related functions."""

    def test_record_thread_publication(self, tmp_registry):
        """Record a thread publication to registry."""
        record_thread_publication(
            canonical_url="https://example.com/article",
            platform="bluesky",
            root_id="at://did:plc:xxx/app.bsky.feed.post/111",
            root_url="https://bsky.app/profile/user/post/111",
            thread_ids=[
                "at://did:plc:xxx/app.bsky.feed.post/111",
                "at://did:plc:xxx/app.bsky.feed.post/222",
                "at://did:plc:xxx/app.bsky.feed.post/333",
            ],
            thread_urls=[
                "https://bsky.app/profile/user/post/111",
                "https://bsky.app/profile/user/post/222",
                "https://bsky.app/profile/user/post/333",
            ],
            title="Test Thread",
            base_path=tmp_registry,
        )

        # Verify it's a thread
        assert is_thread("https://example.com/article", "bluesky", tmp_registry) is True

        # Verify thread IDs
        thread_ids = get_thread_ids("https://example.com/article", "bluesky", tmp_registry)
        assert thread_ids is not None
        assert len(thread_ids) == 3

    def test_is_thread_false_for_regular(self, tmp_registry):
        """Regular publication is not a thread."""
        from crier.registry import record_publication

        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
            base_path=tmp_registry,
        )

        assert is_thread("https://example.com/article", "devto", tmp_registry) is False

    def test_is_thread_nonexistent(self, tmp_registry):
        """Nonexistent article is not a thread."""
        assert is_thread("https://nonexistent.com", "bluesky", tmp_registry) is False

    def test_get_thread_ids_nonexistent(self, tmp_registry):
        """Get thread IDs for nonexistent returns None."""
        ids = get_thread_ids("https://nonexistent.com", "bluesky", tmp_registry)
        assert ids is None


class TestPlatformThreadSupport:
    """Tests for platform thread support."""

    def test_bluesky_supports_threads(self):
        """Bluesky platform supports threads."""
        from crier.platforms.bluesky import Bluesky

        assert Bluesky.supports_threads is True

    def test_mastodon_supports_threads(self):
        """Mastodon platform supports threads."""
        from crier.platforms.mastodon import Mastodon

        assert Mastodon.supports_threads is True

    def test_devto_no_threads(self):
        """DevTo does not support threads."""
        from crier.platforms.devto import DevTo

        assert DevTo.supports_threads is False

    def test_medium_no_threads(self):
        """Medium does not support threads."""
        from crier.platforms.medium import Medium

        assert Medium.supports_threads is False


class TestThreadPublishResult:
    """Tests for ThreadPublishResult dataclass."""

    def test_create_success(self):
        """Create a successful ThreadPublishResult."""
        from crier.platforms.base import ThreadPublishResult, PublishResult

        result = ThreadPublishResult(
            success=True,
            platform="bluesky",
            root_id="at://...",
            root_url="https://...",
            post_ids=["id1", "id2", "id3"],
            post_urls=["url1", "url2", "url3"],
        )

        assert result.success is True
        assert result.platform == "bluesky"
        assert len(result.post_ids) == 3

    def test_create_failure(self):
        """Create a failed ThreadPublishResult."""
        from crier.platforms.base import ThreadPublishResult

        result = ThreadPublishResult(
            success=False,
            platform="bluesky",
            error="Failed to authenticate",
        )

        assert result.success is False
        assert "authenticate" in result.error


class TestCLIThreadOptions:
    """Tests for CLI thread options."""

    def test_publish_help_includes_thread(self, tmp_path, monkeypatch):
        """Publish command help shows thread options."""
        from click.testing import CliRunner
        from crier.cli import cli

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["publish", "--help"])

        assert result.exit_code == 0
        assert "--thread" in result.output
        assert "--thread-style" in result.output
