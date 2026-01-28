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


class TestSplitIntoThreadEdgeCases:
    """Edge case tests for split_into_thread."""

    def test_empty_content(self):
        """Empty content produces empty result."""
        posts = split_into_thread("", max_length=280, style="simple")
        assert posts == []

    def test_whitespace_only_content(self):
        """Whitespace-only content produces empty result."""
        posts = split_into_thread("   \n\n  \t  ", max_length=280, style="simple")
        assert posts == []

    def test_manual_markers_with_empty_segments(self):
        """Manual markers where some segments are empty after stripping."""
        content = "First post.<!-- thread -->  <!-- thread -->Third post."
        posts = split_into_thread(content, max_length=280, style="simple")
        # Empty segments should be filtered out
        assert len(posts) == 2
        assert posts[0] == "First post."
        assert posts[1] == "Third post."

    def test_single_manual_marker_at_start(self):
        """Manual marker at the start produces empty first segment."""
        content = "<!-- thread -->Only post."
        posts = split_into_thread(content, max_length=280, style="simple")
        assert len(posts) == 1
        assert posts[0] == "Only post."

    def test_content_exactly_at_effective_limit(self):
        """Content exactly at the effective limit stays in one post."""
        # effective limit = max_length - 15 = 265 for simple style (no prefix)
        content = "A" * 265
        posts = split_into_thread(content, max_length=280, style="simple")
        assert len(posts) == 1

    def test_paragraphs_combined_when_within_limit(self):
        """Short paragraphs are combined when they fit."""
        content = "Hello.\n\nWorld."
        posts = split_into_thread(content, max_length=280, style="simple")
        assert len(posts) == 1
        assert "Hello." in posts[0]
        assert "World." in posts[0]

    def test_max_posts_truncation_with_numbered(self):
        """Max posts limit is enforced with numbered style."""
        content = "\n\n".join([f"Post {i}." for i in range(30)])
        posts = split_into_thread(content, max_length=30, style="numbered", max_posts=3)
        assert len(posts) <= 3
        # Each post should have x/3 prefix
        assert posts[0].startswith("1/3") or posts[0].startswith("1/")

    def test_long_paragraph_cascades_to_word_split(self):
        """Very long text without sentence boundaries cascades to word-level splitting."""
        # A single long paragraph with no sentence-ending punctuation
        content = " ".join(["word"] * 100)
        posts = split_into_thread(content, max_length=60, style="simple")
        assert len(posts) > 1
        for post in posts:
            assert len(post) <= 60 or post.endswith("...")


class TestSplitBySentencesEdgeCases:
    """Edge case tests for split_by_sentences."""

    def test_single_sentence_within_limit(self):
        """Single sentence within limit returns one chunk."""
        text = "Hello world."
        chunks = split_by_sentences(text, max_length=50)
        assert len(chunks) == 1
        assert chunks[0] == "Hello world."

    def test_oversized_sentence_falls_to_word_split(self):
        """Sentence too long for limit falls back to word splitting."""
        text = "This is a very long sentence that goes on and on without stopping for quite a while"
        chunks = split_by_sentences(text, max_length=30)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk) <= 30 or chunk.endswith("...")

    def test_question_mark_boundary(self):
        """Splits at question mark boundary."""
        text = "Is this first? And this second?"
        chunks = split_by_sentences(text, max_length=20)
        assert len(chunks) >= 2

    def test_exclamation_mark_boundary(self):
        """Splits at exclamation mark boundary."""
        text = "Wow first! Amazing second!"
        chunks = split_by_sentences(text, max_length=20)
        assert len(chunks) >= 2


class TestSplitByWordsEdgeCases:
    """Edge case tests for split_by_words."""

    def test_single_word_within_limit(self):
        """Single word within limit returns one chunk."""
        chunks = split_by_words("hello", max_length=10)
        assert chunks == ["hello"]

    def test_multiple_oversized_words(self):
        """Multiple oversized words are each truncated."""
        text = "abcdefghijklmnop qrstuvwxyzabcdefg"
        chunks = split_by_words(text, max_length=10)
        assert len(chunks) == 2
        for chunk in chunks:
            assert len(chunk) <= 10

    def test_empty_text(self):
        """Empty text returns empty list."""
        chunks = split_by_words("", max_length=10)
        assert chunks == []

    def test_oversized_word_has_ellipsis(self):
        """Truncated word ends with ellipsis."""
        text = "abcdefghijklmnopqrstuvwxyz"
        chunks = split_by_words(text, max_length=10)
        assert len(chunks) == 1
        assert chunks[0].endswith("...")
        assert len(chunks[0]) <= 10


class TestFormatThreadEdgeCases:
    """Edge case tests for format_thread."""

    def test_single_post_too_long_gets_truncated(self):
        """Single post exceeding max_length gets truncated."""
        posts = ["A" * 300]
        formatted = format_thread(posts, style="simple", max_length=100, max_posts=25)
        assert len(formatted) == 1
        assert len(formatted[0]) <= 100
        assert formatted[0].endswith("...")

    def test_max_posts_enforced_in_format(self):
        """format_thread enforces max_posts limit."""
        posts = [f"Post {i}" for i in range(30)]
        formatted = format_thread(posts, style="simple", max_length=280, max_posts=10)
        assert len(formatted) == 10

    def test_empty_posts_list(self):
        """Empty posts list produces empty result."""
        formatted = format_thread([], style="numbered", max_length=280, max_posts=25)
        assert formatted == []

    def test_numbered_post_content_truncation(self):
        """Numbered post content is truncated to fit with prefix."""
        posts = ["A" * 280, "B" * 280]
        formatted = format_thread(posts, style="numbered", max_length=100, max_posts=25)
        for post in formatted:
            assert len(post) <= 100

    def test_emoji_post_content_truncation(self):
        """Emoji style post content is truncated to fit with prefix."""
        posts = ["A" * 280, "B" * 280]
        formatted = format_thread(posts, style="emoji", max_length=100, max_posts=25)
        for post in formatted:
            assert len(post) <= 100


class TestEstimateThreadCountEdgeCases:
    """Edge case tests for estimate_thread_count."""

    def test_empty_content(self):
        """Empty content estimates 0 posts."""
        count = estimate_thread_count("", max_length=280)
        assert count == 0

    def test_exact_boundary_content(self):
        """Content exactly at limit estimates 1 post."""
        # effective limit = 280 - 15 = 265
        content = "A" * 265
        count = estimate_thread_count(content, max_length=280)
        assert count == 1

    def test_custom_max_length(self):
        """Custom max_length affects estimation."""
        content = "\n\n".join(["Short paragraph." for _ in range(5)])
        count_short = estimate_thread_count(content, max_length=30)
        count_long = estimate_thread_count(content, max_length=500)
        assert count_short >= count_long


class TestRegistryThreadEdgeCases:
    """Edge case tests for registry thread functions."""

    def test_record_thread_without_urls(self, tmp_registry):
        """Record thread without optional thread_urls."""
        record_thread_publication(
            canonical_url="https://example.com/no-urls",
            platform="bluesky",
            root_id="at://did:plc:xxx/post/111",
            root_url="https://bsky.app/profile/user/post/111",
            thread_ids=["id1", "id2"],
            base_path=tmp_registry,
        )

        assert is_thread("https://example.com/no-urls", "bluesky", tmp_registry) is True
        ids = get_thread_ids("https://example.com/no-urls", "bluesky", tmp_registry)
        assert ids == ["id1", "id2"]

    def test_record_thread_with_rewrite(self, tmp_registry):
        """Record thread with rewrite metadata."""
        record_thread_publication(
            canonical_url="https://example.com/rewritten",
            platform="mastodon",
            root_id="123",
            root_url="https://mastodon.social/@user/123",
            thread_ids=["123", "124"],
            rewritten=True,
            rewrite_author="claude-code",
            base_path=tmp_registry,
        )

        registry = load_registry(tmp_registry)
        article = registry["articles"]["https://example.com/rewritten"]
        platform_data = article["platforms"]["mastodon"]
        assert platform_data["rewritten"] is True
        assert platform_data["rewrite_author"] == "claude-code"

    def test_get_thread_ids_for_non_thread(self, tmp_registry):
        """get_thread_ids returns None for regular publication."""
        from crier.registry import record_publication

        record_publication(
            canonical_url="https://example.com/regular",
            platform="devto",
            article_id="456",
            url="https://dev.to/regular",
            base_path=tmp_registry,
        )

        ids = get_thread_ids("https://example.com/regular", "devto", tmp_registry)
        assert ids is None

    def test_is_thread_wrong_platform(self, tmp_registry):
        """is_thread returns False for existing article but wrong platform."""
        record_thread_publication(
            canonical_url="https://example.com/threaded",
            platform="bluesky",
            root_id="at://...",
            root_url="https://bsky.app/...",
            thread_ids=["id1", "id2"],
            base_path=tmp_registry,
        )

        assert is_thread("https://example.com/threaded", "mastodon", tmp_registry) is False

    def test_get_thread_ids_wrong_platform(self, tmp_registry):
        """get_thread_ids returns None for existing article but wrong platform."""
        record_thread_publication(
            canonical_url="https://example.com/threaded",
            platform="bluesky",
            root_id="at://...",
            root_url="https://bsky.app/...",
            thread_ids=["id1"],
            base_path=tmp_registry,
        )

        ids = get_thread_ids("https://example.com/threaded", "mastodon", tmp_registry)
        assert ids is None

    def test_record_thread_updates_existing_article(self, tmp_registry):
        """Recording thread for existing article updates metadata."""
        from crier.registry import record_publication

        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
            title="Original Title",
            base_path=tmp_registry,
        )

        record_thread_publication(
            canonical_url="https://example.com/article",
            platform="bluesky",
            root_id="at://...",
            root_url="https://bsky.app/...",
            thread_ids=["id1", "id2"],
            title="Updated Title",
            base_path=tmp_registry,
        )

        registry = load_registry(tmp_registry)
        article = registry["articles"]["https://example.com/article"]
        assert article["title"] == "Updated Title"
        assert "devto" in article["platforms"]
        assert "bluesky" in article["platforms"]
        assert article["platforms"]["bluesky"]["is_thread"] is True

    def test_record_thread_with_source_file_and_hash(self, tmp_registry):
        """Recording thread with source_file and content_hash updates article."""
        record_thread_publication(
            canonical_url="https://example.com/with-meta",
            platform="bluesky",
            root_id="at://...",
            root_url="https://bsky.app/...",
            thread_ids=["id1"],
            source_file="/path/to/article.md",
            content_hash="sha256:abc123",
            base_path=tmp_registry,
        )

        registry = load_registry(tmp_registry)
        article = registry["articles"]["https://example.com/with-meta"]
        assert article["source_file"] == "/path/to/article.md"
        assert article["content_hash"] == "sha256:abc123"


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

    def test_thread_dry_run(self, tmp_path, monkeypatch):
        """Thread mode with dry-run shows thread preview."""
        import yaml
        from click.testing import CliRunner
        from crier.cli import cli

        # Set up config
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config = {
            "platforms": {
                "bluesky": {"api_key": "handle.bsky.social:password"},
            },
        }
        config_file.write_text(yaml.dump(config))
        monkeypatch.setattr("crier.config.DEFAULT_CONFIG_FILE", config_file)
        monkeypatch.setattr("crier.config.DEFAULT_CONFIG_DIR", config_dir)
        monkeypatch.delenv("CRIER_CONFIG", raising=False)

        crier_dir = tmp_path / ".crier"
        crier_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        # Create a markdown file with content
        md_file = tmp_path / "thread.md"
        md_file.write_text("---\ntitle: Thread Test\ncanonical_url: https://example.com/thread\n---\nShort post.")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "publish", str(md_file), "--to", "bluesky", "--thread", "--dry-run"
        ])

        assert result.exit_code == 0
        assert "thread" in result.output.lower() or "Thread" in result.output
