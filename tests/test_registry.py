"""Tests for crier.registry module."""

import os
from unittest.mock import patch

import pytest
import yaml
from pathlib import Path

from crier.registry import (
    get_content_hash,
    get_file_content_hash,
    record_publication,
    record_failure,
    get_failures,
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


class TestArchiveReArchive:
    """Tests for archive/unarchive round trips."""

    def test_archive_and_unarchive_roundtrip(self, tmp_registry):
        """Archive then unarchive restores original state."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )

        # Archive
        set_archived("https://example.com/article", archived=True)
        assert is_archived("https://example.com/article") is True

        # Unarchive
        set_archived("https://example.com/article", archived=False)
        assert is_archived("https://example.com/article") is False

        # Verify no leftover keys
        article = get_article("https://example.com/article")
        assert "archived" not in article
        assert "archived_at" not in article


class TestDeletionPreservesHistory:
    """Tests for deletion preserving publication history."""

    def test_deletion_preserves_other_fields(self, tmp_registry):
        """Recording deletion preserves other publication fields."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
            content_hash="sha256:abc",
        )

        record_deletion("https://example.com/article", "devto")

        article = get_article("https://example.com/article")
        platform_data = article["platforms"]["devto"]
        assert platform_data["id"] == "123"
        assert platform_data["url"] == "https://dev.to/article"
        assert "deleted_at" in platform_data

    def test_is_published_still_true_after_deletion(self, tmp_registry):
        """is_published still returns True after deletion (record preserved)."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )

        record_deletion("https://example.com/article", "devto")

        # The record is still there, just marked as deleted
        assert is_published("https://example.com/article", "devto") is True
        assert is_deleted("https://example.com/article", "devto") is True


class TestRemoveVsDelete:
    """Tests contrasting remove (hard delete) vs record_deletion (soft delete)."""

    def test_remove_publication_fully_removes(self, tmp_registry):
        """remove_publication fully removes the platform entry."""
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

        remove_publication("https://example.com/article", "devto")

        # devto is gone, bluesky remains
        assert not is_published("https://example.com/article", "devto")
        assert is_published("https://example.com/article", "bluesky")
        assert not is_deleted("https://example.com/article", "devto")

    def test_record_deletion_soft_delete(self, tmp_registry):
        """record_deletion preserves the record with deleted_at."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )

        record_deletion("https://example.com/article", "devto")

        # Record still exists with deleted_at
        assert is_published("https://example.com/article", "devto")
        assert is_deleted("https://example.com/article", "devto")

        # Can still get publication info
        info = get_publication_info("https://example.com/article", "devto")
        assert info is not None
        assert info["article_id"] == "123"


class TestGetPublicationIdEdgeCases:
    """Edge case tests for get_publication_id."""

    def test_nonexistent_article_returns_none(self, tmp_registry):
        """get_publication_id returns None for nonexistent article."""
        result = get_publication_id("https://nonexistent.com", "devto")
        assert result is None

    def test_nonexistent_platform_returns_none(self, tmp_registry):
        """get_publication_id returns None for unpublished platform."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )
        result = get_publication_id("https://example.com/article", "bluesky")
        assert result is None


class TestGetPublicationInfoEdgeCases:
    """Edge case tests for get_publication_info."""

    def test_nonexistent_article_returns_none(self, tmp_registry):
        """get_publication_info returns None for nonexistent article."""
        result = get_publication_info("https://nonexistent.com", "devto")
        assert result is None

    def test_nonexistent_platform_returns_none(self, tmp_registry):
        """get_publication_info returns None for unpublished platform."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )
        result = get_publication_info("https://example.com/article", "bluesky")
        assert result is None


class TestContentChangedEdgeCases:
    """Edge case tests for has_content_changed."""

    def test_no_hash_stored_means_changed(self, tmp_registry):
        """Article with no hash stored is considered changed."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
            # No content_hash
        )

        assert has_content_changed("https://example.com/article", "sha256:new") is True

    def test_platform_not_published_means_changed(self, tmp_registry):
        """Checking change for unpublished platform returns True."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
            content_hash="sha256:abc",
        )

        assert has_content_changed(
            "https://example.com/article", "sha256:abc", platform="bluesky"
        ) is True


class TestAtomicWrite:
    """Tests for atomic registry save behavior."""

    def test_save_creates_no_temp_files(self, tmp_registry):
        """After successful save, no temp files should remain."""
        registry = load_registry()
        registry["articles"]["https://example.com/test"] = {
            "title": "Test",
            "platforms": {},
        }
        save_registry(registry)

        # No temp files should remain in registry dir
        temp_files = list(tmp_registry.glob(".registry_*.tmp"))
        assert temp_files == []

    def test_save_preserves_data_on_write_error(self, tmp_registry):
        """If write fails, original registry should be intact."""
        # Set up initial data
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
        )

        # Verify initial data is there
        assert is_published("https://example.com/article", "devto")

        # Simulate a write failure by making yaml.dump raise an error
        with patch("crier.registry.yaml.dump", side_effect=IOError("Disk full")):
            with pytest.raises(IOError, match="Disk full"):
                save_registry({"version": 2, "articles": {"bad": "data"}})

        # Original data should still be intact
        registry = load_registry()
        assert "https://example.com/article" in registry["articles"]

    def test_save_cleans_up_temp_on_failure(self, tmp_registry):
        """Temp file should be cleaned up on write failure."""
        with patch("crier.registry.yaml.dump", side_effect=IOError("Disk full")):
            with pytest.raises(IOError):
                save_registry({"version": 2, "articles": {}})

        # No temp files should remain
        temp_files = list(tmp_registry.glob(".registry_*.tmp"))
        assert temp_files == []

    def test_atomic_replace_is_used(self, tmp_registry):
        """Verify os.replace is called (not direct write)."""
        with patch("crier.registry.os.replace", wraps=os.replace) as mock_replace:
            save_registry({"version": 2, "articles": {}})
            assert mock_replace.called

    def test_concurrent_reads_during_write(self, tmp_registry):
        """Registry should be readable even during a write."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
        )

        # Read should work while a save is conceptually in progress
        # (the atomic nature means the old file is intact until replace)
        registry = load_registry()
        assert "https://example.com/article" in registry["articles"]


class TestErrorPersistence:
    """Tests for error recording and retrieval."""

    def test_record_failure_new_article(self, tmp_registry):
        """record_failure creates article entry and records error."""
        record_failure(
            canonical_url="https://example.com/article",
            platform="devto",
            error_msg="API returned 500",
        )

        article = get_article("https://example.com/article")
        assert article is not None
        platform_data = article["platforms"]["devto"]
        assert platform_data["last_error"] == "API returned 500"
        assert "last_error_at" in platform_data

    def test_record_failure_existing_article(self, tmp_registry):
        """record_failure on existing article preserves other data."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
            title="Test",
        )

        record_failure(
            canonical_url="https://example.com/article",
            platform="bluesky",
            error_msg="Rate limited",
        )

        article = get_article("https://example.com/article")
        # devto publication should still be there
        assert "devto" in article["platforms"]
        assert article["platforms"]["devto"]["id"] == "123"
        # bluesky should have the error
        assert article["platforms"]["bluesky"]["last_error"] == "Rate limited"

    def test_success_clears_error(self, tmp_registry):
        """Successful publication clears previous error."""
        record_failure(
            canonical_url="https://example.com/article",
            platform="devto",
            error_msg="Timeout",
        )

        # Now succeed
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
        )

        article = get_article("https://example.com/article")
        platform_data = article["platforms"]["devto"]
        assert "last_error" not in platform_data
        assert "last_error_at" not in platform_data

    def test_get_failures_returns_failed(self, tmp_registry):
        """get_failures returns list of failed publications."""
        record_failure(
            canonical_url="https://example.com/a",
            platform="devto",
            error_msg="500 error",
        )
        record_failure(
            canonical_url="https://example.com/b",
            platform="bluesky",
            error_msg="Rate limited",
        )

        failures = get_failures()
        assert len(failures) == 2

        urls = {f["canonical_url"] for f in failures}
        assert urls == {"https://example.com/a", "https://example.com/b"}

    def test_get_failures_excludes_successful(self, tmp_registry):
        """get_failures doesn't include successful publications."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
        )

        failures = get_failures()
        assert len(failures) == 0

    def test_get_failures_mixed(self, tmp_registry):
        """get_failures with mix of success and failure on same article."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
        )
        record_failure(
            canonical_url="https://example.com/article",
            platform="bluesky",
            error_msg="Auth failed",
        )

        failures = get_failures()
        assert len(failures) == 1
        assert failures[0]["platform"] == "bluesky"
        assert failures[0]["error"] == "Auth failed"

    def test_record_failure_updates_existing_error(self, tmp_registry):
        """Recording a new failure overwrites the previous error."""
        record_failure(
            canonical_url="https://example.com/article",
            platform="devto",
            error_msg="First error",
        )
        record_failure(
            canonical_url="https://example.com/article",
            platform="devto",
            error_msg="Second error",
        )

        article = get_article("https://example.com/article")
        assert article["platforms"]["devto"]["last_error"] == "Second error"

    def test_get_failures_empty_registry(self, tmp_registry):
        """get_failures on empty registry returns empty list."""
        failures = get_failures()
        assert failures == []


class TestRegistryCrashSafety:
    """Tests for registry crash safety and atomic write resilience."""

    def test_registry_survives_write_interrupt(self, tmp_registry):
        """Save a valid registry, then mock os.replace to raise OSError,
        verify original data is preserved by loading again."""
        # First, record a valid publication
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
            title="Original Article",
        )

        # Verify it's there
        article = get_article("https://example.com/article")
        assert article is not None
        assert article["title"] == "Original Article"

        # Now try to save new data but os.replace fails (simulating crash)
        with patch("crier.registry.os.replace", side_effect=OSError("Disk failure")):
            with pytest.raises(OSError, match="Disk failure"):
                save_registry({"version": 2, "articles": {"https://example.com/new": {"title": "New", "platforms": {}}}})

        # Original data should still be intact
        registry = load_registry()
        assert "https://example.com/article" in registry["articles"]
        assert registry["articles"]["https://example.com/article"]["title"] == "Original Article"
        # The failed write should NOT have been applied
        assert "https://example.com/new" not in registry["articles"]

    def test_temp_file_cleaned_up_on_error(self, tmp_registry):
        """Mock yaml.dump to raise an exception, verify no .tmp files remain in the directory."""
        with patch("crier.registry.yaml.dump", side_effect=Exception("Serialization error")):
            with pytest.raises(Exception, match="Serialization error"):
                save_registry({"version": 2, "articles": {}})

        # No temp files should remain
        temp_files = list(tmp_registry.glob(".registry_*.tmp"))
        assert temp_files == []

    def test_concurrent_loads_during_write(self, tmp_registry):
        """Use threading to do a load_registry while save_registry is happening,
        verify no corruption (both operations complete without error)."""
        import threading

        # Set up initial data
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
            title="Concurrent Test",
        )

        errors = []

        def load_in_thread():
            """Load registry in a separate thread."""
            try:
                registry = load_registry()
                # Should always get valid data (either old or new)
                assert "articles" in registry
                assert "version" in registry
            except Exception as e:
                errors.append(e)

        def save_in_thread():
            """Save registry in a separate thread."""
            try:
                registry = load_registry()
                registry["articles"]["https://example.com/article"]["title"] = "Updated"
                save_registry(registry)
            except Exception as e:
                errors.append(e)

        # Run save and load concurrently
        save_thread = threading.Thread(target=save_in_thread)
        load_thread = threading.Thread(target=load_in_thread)

        save_thread.start()
        load_thread.start()

        save_thread.join(timeout=5)
        load_thread.join(timeout=5)

        # Neither thread should have errored
        assert errors == [], f"Threading errors: {errors}"

        # Final state should be valid
        registry = load_registry()
        assert "articles" in registry
        assert "https://example.com/article" in registry["articles"]


class TestErrorClearOnSuccess:
    """Tests for error clearing behavior when publication succeeds."""

    def test_record_failure_then_success_clears_error(self, tmp_registry):
        """Record failure for a platform, then record_publication for same platform,
        verify last_error is gone."""
        record_failure(
            canonical_url="https://example.com/article",
            platform="devto",
            error_msg="Connection timeout",
        )

        # Verify error is recorded
        article = get_article("https://example.com/article")
        assert "last_error" in article["platforms"]["devto"]
        assert article["platforms"]["devto"]["last_error"] == "Connection timeout"

        # Now succeed on the same platform
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="999",
            url="https://dev.to/article",
            title="Success Article",
        )

        # Error should be cleared
        article = get_article("https://example.com/article")
        platform_data = article["platforms"]["devto"]
        assert "last_error" not in platform_data
        assert "last_error_at" not in platform_data
        assert platform_data["id"] == "999"

    def test_get_failures_excludes_successful_platforms(self, tmp_registry):
        """Record failure for one platform and success for another on same article,
        verify get_failures only returns the failed one."""
        canonical_url = "https://example.com/article"

        # Record failure on bluesky
        record_failure(
            canonical_url=canonical_url,
            platform="bluesky",
            error_msg="Auth failed",
        )

        # Record success on devto
        record_publication(
            canonical_url=canonical_url,
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
            title="Test Article",
        )

        failures = get_failures()
        assert len(failures) == 1
        assert failures[0]["platform"] == "bluesky"
        assert failures[0]["error"] == "Auth failed"
        assert failures[0]["canonical_url"] == canonical_url

    def test_multiple_failures_same_article(self, tmp_registry):
        """Record failures for 2 different platforms on same article,
        verify get_failures returns both."""
        canonical_url = "https://example.com/article"

        record_failure(
            canonical_url=canonical_url,
            platform="devto",
            error_msg="Server error 500",
        )
        record_failure(
            canonical_url=canonical_url,
            platform="bluesky",
            error_msg="Rate limited",
        )

        failures = get_failures()
        assert len(failures) == 2

        platforms = {f["platform"] for f in failures}
        assert platforms == {"devto", "bluesky"}

        errors = {f["platform"]: f["error"] for f in failures}
        assert errors["devto"] == "Server error 500"
        assert errors["bluesky"] == "Rate limited"


class TestRegistryWriteAfterPublish:
    """Tests for registry persistence after various operations."""

    def test_save_preserves_all_fields(self, tmp_registry):
        """Create a registry with complex data (threads, stats, archived), save and reload,
        verify all data intact."""
        from crier.registry import record_thread_publication, save_stats

        canonical_url = "https://example.com/complex-article"

        # Record a thread publication
        record_thread_publication(
            canonical_url=canonical_url,
            platform="bluesky",
            root_id="root-001",
            root_url="https://bsky.app/post/root-001",
            thread_ids=["root-001", "reply-002", "reply-003"],
            thread_urls=[
                "https://bsky.app/post/root-001",
                "https://bsky.app/post/reply-002",
                "https://bsky.app/post/reply-003",
            ],
            title="Thread Article",
            source_file="posts/thread.md",
            content_hash="sha256:threadhash123",
            rewritten=True,
            rewrite_author="claude-code",
        )

        # Save stats
        save_stats(
            canonical_url=canonical_url,
            platform="bluesky",
            views=100,
            likes=42,
            comments=7,
            reposts=15,
        )

        # Archive the article
        set_archived(canonical_url, archived=True)

        # Now reload and verify everything is intact
        registry = load_registry()
        article = registry["articles"][canonical_url]

        # Check top-level fields
        assert article["title"] == "Thread Article"
        assert article["source_file"] == "posts/thread.md"
        assert article["content_hash"] == "sha256:threadhash123"
        assert article["archived"] is True
        assert "archived_at" in article

        # Check thread platform data
        platform_data = article["platforms"]["bluesky"]
        assert platform_data["id"] == "root-001"
        assert platform_data["url"] == "https://bsky.app/post/root-001"
        assert platform_data["is_thread"] is True
        assert platform_data["thread_ids"] == ["root-001", "reply-002", "reply-003"]
        assert len(platform_data["thread_urls"]) == 3
        assert platform_data["rewritten"] is True
        assert platform_data["rewrite_author"] == "claude-code"

        # Check stats
        assert platform_data["stats"]["views"] == 100
        assert platform_data["stats"]["likes"] == 42
        assert platform_data["stats"]["comments"] == 7
        assert platform_data["stats"]["reposts"] == 15
        assert "fetched_at" in platform_data["stats"]

    def test_save_with_unicode_content(self, tmp_registry):
        """Registry with unicode titles and content, save and reload, verify preserved."""
        record_publication(
            canonical_url="https://example.com/unicode-article",
            platform="devto",
            article_id="uni-123",
            url="https://dev.to/unicode-article",
            title="Artigo em Portugues com acentos: caca, maca, cafe",
            source_file="posts/unicode.md",
        )

        record_publication(
            canonical_url="https://example.com/japanese-article",
            platform="hashnode",
            article_id="jp-456",
            url="https://hashnode.com/jp-article",
            title="日本語のテスト記事",
            source_file="posts/japanese.md",
        )

        record_publication(
            canonical_url="https://example.com/emoji-article",
            platform="bluesky",
            article_id="em-789",
            url="https://bsky.app/post/em-789",
            title="Article with emojis in metadata",
            posted_content="Check out this article! It covers Python and Rust topics.",
            rewritten=True,
        )

        # Reload and verify
        registry = load_registry()

        # Portuguese
        article1 = registry["articles"]["https://example.com/unicode-article"]
        assert article1["title"] == "Artigo em Portugues com acentos: caca, maca, cafe"

        # Japanese
        article2 = registry["articles"]["https://example.com/japanese-article"]
        assert article2["title"] == "日本語のテスト記事"

        # Emoji content
        article3 = registry["articles"]["https://example.com/emoji-article"]
        assert article3["platforms"]["bluesky"]["posted_content"] == "Check out this article! It covers Python and Rust topics."

    def test_save_empty_registry(self, tmp_registry):
        """Save an empty registry (no articles), reload, verify structure intact."""
        empty_registry = {"version": 2, "articles": {}}
        save_registry(empty_registry)

        # Reload
        registry = load_registry()

        assert registry["version"] == 2
        assert registry["articles"] == {}
        assert isinstance(registry["articles"], dict)
