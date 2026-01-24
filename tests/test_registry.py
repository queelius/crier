"""Tests for crier.registry module."""

import pytest
from pathlib import Path

from crier.registry import (
    get_content_hash,
    get_file_content_hash,
    record_publication,
    is_published,
    has_content_changed,
    get_article,
    get_article_by_file,
    get_all_articles,
    get_platform_publications,
    get_publication_info,
    get_publication_id,
    remove_article,
    remove_publication,
    record_deletion,
    is_deleted,
    set_archived,
    is_archived,
    load_registry,
    save_registry,
)


class TestContentHash:
    """Tests for content hashing functions."""

    def test_get_content_hash(self):
        content = "Hello, world!"
        hash1 = get_content_hash(content)
        hash2 = get_content_hash(content)
        assert hash1 == hash2
        assert hash1.startswith("sha256:")

    def test_different_content_different_hash(self):
        hash1 = get_content_hash("Content A")
        hash2 = get_content_hash("Content B")
        assert hash1 != hash2

    def test_get_file_content_hash(self, tmp_path):
        test_file = tmp_path / "test.md"
        test_file.write_text("File content here")
        hash1 = get_file_content_hash(test_file)
        assert hash1.startswith("sha256:")

        # Same content = same hash
        hash2 = get_file_content_hash(test_file)
        assert hash1 == hash2

    def test_file_hash_changes_with_content(self, tmp_path):
        test_file = tmp_path / "test.md"
        test_file.write_text("Original content")
        hash1 = get_file_content_hash(test_file)

        test_file.write_text("Modified content")
        hash2 = get_file_content_hash(test_file)

        assert hash1 != hash2


class TestRecordPublication:
    """Tests for record_publication()."""

    def test_record_new_publication(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="12345",
            url="https://dev.to/user/article",
            title="Test Article",
            source_file="posts/test.md",
        )

        article = get_article("https://example.com/article")
        assert article is not None
        assert article["title"] == "Test Article"
        assert "devto" in article["platforms"]
        assert article["platforms"]["devto"]["id"] == "12345"

    def test_record_multiple_platforms(self, tmp_registry):
        canonical_url = "https://example.com/article"

        record_publication(
            canonical_url=canonical_url,
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
            title="Test",
        )
        record_publication(
            canonical_url=canonical_url,
            platform="bluesky",
            article_id="456",
            url="https://bsky.app/post/456",
        )

        article = get_article(canonical_url)
        assert "devto" in article["platforms"]
        assert "bluesky" in article["platforms"]

    def test_record_with_rewrite(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="bluesky",
            article_id="123",
            url="https://bsky.app/post/123",
            rewritten=True,
            rewrite_author="claude-code",
            posted_content="Short announcement text",
        )

        article = get_article("https://example.com/article")
        platform_data = article["platforms"]["bluesky"]
        assert platform_data["rewritten"] is True
        assert platform_data["rewrite_author"] == "claude-code"
        assert platform_data["posted_content"] == "Short announcement text"

    def test_record_with_content_hash(self, tmp_registry):
        content_hash = "sha256:abc123"
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
            content_hash=content_hash,
        )

        article = get_article("https://example.com/article")
        assert article["content_hash"] == content_hash
        assert article["platforms"]["devto"]["content_hash"] == content_hash


class TestIsPublished:
    """Tests for is_published()."""

    def test_not_published(self, tmp_registry):
        assert is_published("https://example.com/new", "devto") is False

    def test_is_published(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )
        assert is_published("https://example.com/article", "devto") is True
        assert is_published("https://example.com/article", "bluesky") is False


class TestHasContentChanged:
    """Tests for has_content_changed()."""

    def test_new_article_is_changed(self, tmp_registry):
        assert has_content_changed("https://example.com/new", "sha256:abc") is True

    def test_same_hash_not_changed(self, tmp_registry):
        content_hash = "sha256:abc123"
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
            content_hash=content_hash,
        )
        assert has_content_changed("https://example.com/article", content_hash) is False

    def test_different_hash_is_changed(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
            content_hash="sha256:original",
        )
        assert has_content_changed("https://example.com/article", "sha256:modified") is True

    def test_check_against_platform(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
            content_hash="sha256:v1",
        )
        # Updated to bluesky with different hash
        record_publication(
            canonical_url="https://example.com/article",
            platform="bluesky",
            article_id="456",
            url=None,
            content_hash="sha256:v2",
        )

        # Check against specific platform
        assert has_content_changed(
            "https://example.com/article", "sha256:v1", platform="devto"
        ) is False
        assert has_content_changed(
            "https://example.com/article", "sha256:v2", platform="bluesky"
        ) is False
        assert has_content_changed(
            "https://example.com/article", "sha256:v3", platform="devto"
        ) is True


class TestGetArticle:
    """Tests for get_article functions."""

    def test_get_nonexistent_article(self, tmp_registry):
        assert get_article("https://example.com/nonexistent") is None

    def test_get_article_by_canonical_url(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
            title="My Article",
        )
        article = get_article("https://example.com/article")
        assert article is not None
        assert article["title"] == "My Article"

    def test_get_article_by_file(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
            source_file="posts/my-article.md",
        )
        result = get_article_by_file("posts/my-article.md")
        assert result is not None
        canonical_url, article = result
        assert canonical_url == "https://example.com/article"

    def test_get_article_by_file_not_found(self, tmp_registry):
        assert get_article_by_file("nonexistent.md") is None

    def test_get_all_articles(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article1",
            platform="devto",
            article_id="1",
            url=None,
        )
        record_publication(
            canonical_url="https://example.com/article2",
            platform="devto",
            article_id="2",
            url=None,
        )
        articles = get_all_articles()
        assert len(articles) == 2
        assert "https://example.com/article1" in articles
        assert "https://example.com/article2" in articles


class TestGetPlatformPublications:
    """Tests for get_platform_publications()."""

    def test_empty_platform(self, tmp_registry):
        pubs = get_platform_publications("devto")
        assert pubs == []

    def test_get_platform_publications(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article1",
            platform="devto",
            article_id="1",
            url="https://dev.to/article1",
            title="Article 1",
        )
        record_publication(
            canonical_url="https://example.com/article2",
            platform="devto",
            article_id="2",
            url="https://dev.to/article2",
            title="Article 2",
        )
        record_publication(
            canonical_url="https://example.com/article1",
            platform="bluesky",
            article_id="3",
            url="https://bsky.app/post/3",
        )

        devto_pubs = get_platform_publications("devto")
        assert len(devto_pubs) == 2

        bluesky_pubs = get_platform_publications("bluesky")
        assert len(bluesky_pubs) == 1


class TestGetPublicationInfo:
    """Tests for get_publication_info() and get_publication_id()."""

    def test_get_publication_id(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="12345",
            url=None,
        )
        assert get_publication_id("https://example.com/article", "devto") == "12345"
        assert get_publication_id("https://example.com/article", "bluesky") is None

    def test_get_publication_info(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="12345",
            url="https://dev.to/article",
            content_hash="sha256:abc",
        )
        info = get_publication_info("https://example.com/article", "devto")
        assert info is not None
        assert info["article_id"] == "12345"
        assert info["url"] == "https://dev.to/article"
        assert info["content_hash"] == "sha256:abc"
        assert "published_at" in info

    def test_get_publication_info_not_found(self, tmp_registry):
        assert get_publication_info("https://example.com/none", "devto") is None


class TestRemoveOperations:
    """Tests for remove_article() and remove_publication()."""

    def test_remove_article(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )
        assert remove_article("https://example.com/article") is True
        assert get_article("https://example.com/article") is None

    def test_remove_nonexistent_article(self, tmp_registry):
        assert remove_article("https://example.com/nonexistent") is False

    def test_remove_publication(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )
        record_publication(
            canonical_url="https://example.com/article",
            platform="bluesky",
            article_id="456",
            url=None,
        )

        assert remove_publication("https://example.com/article", "devto") is True
        article = get_article("https://example.com/article")
        assert "devto" not in article["platforms"]
        assert "bluesky" in article["platforms"]

    def test_remove_nonexistent_publication(self, tmp_registry):
        assert remove_publication("https://example.com/article", "devto") is False


class TestDeletionOperations:
    """Tests for record_deletion() and is_deleted()."""

    def test_record_deletion_success(self, tmp_registry):
        """Recording deletion adds deleted_at timestamp."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
        )

        assert record_deletion("https://example.com/article", "devto") is True

        # Verify deleted_at was added
        article = get_article("https://example.com/article")
        assert "deleted_at" in article["platforms"]["devto"]

    def test_record_deletion_article_not_found(self, tmp_registry):
        """Recording deletion fails if article doesn't exist."""
        assert record_deletion("https://example.com/nonexistent", "devto") is False

    def test_record_deletion_platform_not_found(self, tmp_registry):
        """Recording deletion fails if platform doesn't exist."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )
        assert record_deletion("https://example.com/article", "bluesky") is False

    def test_is_deleted_true(self, tmp_registry):
        """is_deleted returns True for deleted publications."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )
        record_deletion("https://example.com/article", "devto")

        assert is_deleted("https://example.com/article", "devto") is True

    def test_is_deleted_false(self, tmp_registry):
        """is_deleted returns False for non-deleted publications."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )

        assert is_deleted("https://example.com/article", "devto") is False

    def test_is_deleted_article_not_found(self, tmp_registry):
        """is_deleted returns False for nonexistent article."""
        assert is_deleted("https://example.com/nonexistent", "devto") is False

    def test_is_deleted_platform_not_found(self, tmp_registry):
        """is_deleted returns False for nonexistent platform."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )
        assert is_deleted("https://example.com/article", "bluesky") is False


class TestArchiveOperations:
    """Tests for set_archived() and is_archived()."""

    def test_set_archived_true(self, tmp_registry):
        """Setting archived=True adds archived flag and timestamp."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )

        assert set_archived("https://example.com/article", archived=True) is True

        article = get_article("https://example.com/article")
        assert article["archived"] is True
        assert "archived_at" in article

    def test_set_archived_false(self, tmp_registry):
        """Setting archived=False removes archived flag and timestamp."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )
        set_archived("https://example.com/article", archived=True)

        assert set_archived("https://example.com/article", archived=False) is True

        article = get_article("https://example.com/article")
        assert "archived" not in article
        assert "archived_at" not in article

    def test_set_archived_article_not_found(self, tmp_registry):
        """Setting archived fails for nonexistent article."""
        assert set_archived("https://example.com/nonexistent", archived=True) is False

    def test_is_archived_true(self, tmp_registry):
        """is_archived returns True for archived articles."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )
        set_archived("https://example.com/article", archived=True)

        assert is_archived("https://example.com/article") is True

    def test_is_archived_false(self, tmp_registry):
        """is_archived returns False for non-archived articles."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )

        assert is_archived("https://example.com/article") is False

    def test_is_archived_article_not_found(self, tmp_registry):
        """is_archived returns False for nonexistent article."""
        assert is_archived("https://example.com/nonexistent") is False
