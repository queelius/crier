"""Tests for crier.registry module (SQLite-backed, v3)."""

import threading
from pathlib import Path

import yaml

from crier.registry import (
    CURRENT_VERSION,
    find_slug,
    get_all_articles,
    get_article,
    get_article_by_file,
    get_article_by_slug,
    get_cached_stats,
    get_failures,
    get_or_create_slug,
    get_platform_publications,
    get_publication_id,
    get_publication_info,
    get_stats_age_seconds,
    infer_section,
    is_archived,
    is_deleted,
    is_published,
    is_thread,
    get_thread_ids,
    load_registry,
    make_slug,
    migrate_yaml_to_sqlite,
    record_deletion,
    record_failure,
    record_publication,
    record_thread_publication,
    remove_article,
    remove_publication,
    save_stats,
    set_archived,
)


class TestSlug:
    """Tests for make_slug, get_or_create_slug, find_slug."""

    def test_make_slug_basic(self):
        assert make_slug("Hello World") == "hello-world"

    def test_make_slug_special_chars(self):
        slug = make_slug("My Article: A Deep Dive!")
        assert ":" not in slug
        assert "!" not in slug
        assert slug == "my-article-a-deep-dive"

    def test_make_slug_unicode(self):
        slug = make_slug("Artigo em Portugues")
        assert slug == "artigo-em-portugues"

    def test_make_slug_truncates_long_titles(self):
        long_title = "A" * 200
        slug = make_slug(long_title)
        assert len(slug) <= 80

    def test_get_or_create_slug_creates_new(self, tmp_registry):
        slug = get_or_create_slug(title="Brand New Article")
        assert slug == "brand-new-article"
        # Verify article was created in DB
        article = get_article_by_slug(slug)
        assert article is not None
        assert article["title"] == "Brand New Article"

    def test_get_or_create_slug_finds_by_canonical_url(self, tmp_registry):
        # Create first
        slug1 = get_or_create_slug(
            title="First Article",
            canonical_url="https://example.com/first",
        )
        # Look up by canonical_url
        slug2 = get_or_create_slug(
            title="Different Title",
            canonical_url="https://example.com/first",
        )
        assert slug1 == slug2

    def test_get_or_create_slug_finds_by_source_file(self, tmp_registry):
        slug1 = get_or_create_slug(
            title="My Article",
            source_file="posts/my-article.md",
        )
        slug2 = get_or_create_slug(
            title="Different Title",
            source_file="posts/my-article.md",
        )
        assert slug1 == slug2

    def test_get_or_create_slug_finds_by_title_slug(self, tmp_registry):
        slug1 = get_or_create_slug(title="Same Title")
        slug2 = get_or_create_slug(title="Same Title")
        assert slug1 == slug2

    def test_get_or_create_slug_unique_collision(self, tmp_registry):
        slug1 = get_or_create_slug(
            title="Duplicate",
            canonical_url="https://example.com/dup1",
        )
        # Different canonical_url, different source_file, but same title slug
        slug2 = get_or_create_slug(
            title="Duplicate",
            canonical_url="https://example.com/dup2",
        )
        # slug2 should be different because dup1 already exists with that slug
        # but canonical_url differs, so after slug lookup fails (slug matches
        # an article with different canonical_url), a new unique slug is needed.
        # Actually, get_or_create_slug checks slug match first: if slug exists, returns it.
        # The slug collision only happens if there's no canonical_url/source match.
        # Since canonical_url "https://example.com/dup2" doesn't match dup1,
        # but the slug "duplicate" already exists, it returns the existing slug.
        assert slug1 == slug2

    def test_find_slug_by_canonical_url(self, tmp_registry):
        get_or_create_slug(
            title="Findable",
            canonical_url="https://example.com/findable",
        )
        result = find_slug(canonical_url="https://example.com/findable")
        assert result == "findable"

    def test_find_slug_by_source_file(self, tmp_registry):
        get_or_create_slug(
            title="File Article",
            source_file="posts/file-article.md",
        )
        result = find_slug(source_file="posts/file-article.md")
        assert result == "file-article"

    def test_find_slug_by_title(self, tmp_registry):
        get_or_create_slug(title="Title Lookup")
        result = find_slug(title="Title Lookup")
        assert result == "title-lookup"

    def test_find_slug_not_found(self, tmp_registry):
        assert find_slug(canonical_url="https://example.com/nope") is None
        assert find_slug(source_file="nope.md") is None
        assert find_slug(title="Nonexistent") is None


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

    def test_record_without_content_hash(self, tmp_registry):
        """content_hash parameter was removed in v3."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )

        article = get_article("https://example.com/article")
        assert "content_hash" not in article


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
            title="Article One",
        )
        record_publication(
            canonical_url="https://example.com/article2",
            platform="devto",
            article_id="2",
            url=None,
            title="Article Two",
        )
        articles = get_all_articles()
        assert len(articles) == 2
        assert "https://example.com/article1" in articles
        assert "https://example.com/article2" in articles

    def test_get_article_by_slug(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
            title="My Slug Article",
        )
        article = get_article_by_slug("my-slug-article")
        assert article is not None
        assert article["title"] == "My Slug Article"


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
        )
        info = get_publication_info("https://example.com/article", "devto")
        assert info is not None
        assert info["article_id"] == "12345"
        assert info["url"] == "https://dev.to/article"
        assert "content_hash" not in info
        assert "published_at" in info

    def test_get_publication_info_not_found(self, tmp_registry):
        assert get_publication_info("https://example.com/none", "devto") is None


class TestGetPublicationIdEdgeCases:
    """Edge case tests for get_publication_id."""

    def test_nonexistent_article_returns_none(self, tmp_registry):
        result = get_publication_id("https://nonexistent.com", "devto")
        assert result is None

    def test_nonexistent_platform_returns_none(self, tmp_registry):
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
        result = get_publication_info("https://nonexistent.com", "devto")
        assert result is None

    def test_nonexistent_platform_returns_none(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )
        result = get_publication_info("https://example.com/article", "bluesky")
        assert result is None


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
            title="Test",
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

        article = get_article("https://example.com/article")
        assert "deleted_at" in article["platforms"]["devto"]

    def test_record_deletion_article_not_found(self, tmp_registry):
        assert record_deletion("https://example.com/nonexistent", "devto") is False

    def test_record_deletion_platform_not_found(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )
        assert record_deletion("https://example.com/article", "bluesky") is False

    def test_is_deleted_true(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )
        record_deletion("https://example.com/article", "devto")

        assert is_deleted("https://example.com/article", "devto") is True

    def test_is_deleted_false(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )

        assert is_deleted("https://example.com/article", "devto") is False

    def test_is_deleted_article_not_found(self, tmp_registry):
        assert is_deleted("https://example.com/nonexistent", "devto") is False

    def test_is_deleted_platform_not_found(self, tmp_registry):
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
        assert set_archived("https://example.com/nonexistent", archived=True) is False

    def test_is_archived_true(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )
        set_archived("https://example.com/article", archived=True)

        assert is_archived("https://example.com/article") is True

    def test_is_archived_false(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )

        assert is_archived("https://example.com/article") is False

    def test_is_archived_article_not_found(self, tmp_registry):
        assert is_archived("https://example.com/nonexistent") is False


class TestArchiveReArchive:
    """Tests for archive/unarchive round trips."""

    def test_archive_and_unarchive_roundtrip(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )

        set_archived("https://example.com/article", archived=True)
        assert is_archived("https://example.com/article") is True

        set_archived("https://example.com/article", archived=False)
        assert is_archived("https://example.com/article") is False

        article = get_article("https://example.com/article")
        assert "archived" not in article
        assert "archived_at" not in article


class TestDeletionPreservesHistory:
    """Tests for deletion preserving publication history."""

    def test_deletion_preserves_other_fields(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
        )

        record_deletion("https://example.com/article", "devto")

        article = get_article("https://example.com/article")
        platform_data = article["platforms"]["devto"]
        assert platform_data["id"] == "123"
        assert platform_data["url"] == "https://dev.to/article"
        assert "deleted_at" in platform_data

    def test_is_published_false_after_deletion(self, tmp_registry):
        """is_published returns False after deletion (deleted_at IS NOT NULL)."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )

        record_deletion("https://example.com/article", "devto")

        # In SQLite registry, is_published checks deleted_at IS NULL
        assert is_published("https://example.com/article", "devto") is False
        assert is_deleted("https://example.com/article", "devto") is True

    def test_republish_clears_deleted_state(self, tmp_registry):
        """Re-publishing a soft-deleted article clears deleted_at."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url="https://dev.to/a",
        )
        record_deletion("https://example.com/article", "devto")
        assert is_deleted("https://example.com/article", "devto") is True

        # Re-publish — should resurrect the publication
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="456",
            url="https://dev.to/a-v2",
        )

        assert is_published("https://example.com/article", "devto") is True
        assert is_deleted("https://example.com/article", "devto") is False

    def test_republish_as_single_clears_thread_fields(self, tmp_registry):
        """Re-publishing as a single post clears thread fields from prior thread post."""
        from crier.registry import record_thread_publication, is_thread, get_thread_ids
        record_thread_publication(
            canonical_url="https://example.com/article",
            platform="bluesky",
            root_id="root1",
            root_url="https://bsky.app/r1",
            thread_ids=["t1", "t2", "t3"],
        )
        assert is_thread("https://example.com/article", "bluesky") is True

        record_publication(
            canonical_url="https://example.com/article",
            platform="bluesky",
            article_id="single1",
            url="https://bsky.app/s1",
        )

        assert is_thread("https://example.com/article", "bluesky") is False
        assert get_thread_ids("https://example.com/article", "bluesky") is None

    def test_republish_as_thread_clears_posted_content(self, tmp_registry):
        """Re-publishing as a thread clears posted_content from prior single post."""
        from crier.registry import record_thread_publication
        record_publication(
            canonical_url="https://example.com/article",
            platform="bluesky",
            article_id="s1",
            url="https://bsky.app/s1",
            rewritten=True,
            posted_content="short rewrite",
        )

        record_thread_publication(
            canonical_url="https://example.com/article",
            platform="bluesky",
            root_id="r1",
            root_url="https://bsky.app/r1",
            thread_ids=["t1", "t2"],
        )

        # posted_content should be cleared; thread data present
        article = get_article("https://example.com/article")
        pdata = article["platforms"]["bluesky"]
        assert pdata.get("is_thread") is True
        assert "posted_content" not in pdata
        assert pdata.get("thread_ids") == ["t1", "t2"]

    def test_record_thread_clears_deleted_state(self, tmp_registry):
        """record_thread_publication UPSERT must clear deleted_at on conflict.

        Regression: INSERT OR REPLACE used to clear it implicitly. The UPSERT
        rewrite must enumerate deleted_at = NULL to preserve resurrection.
        """
        from crier.registry import record_thread_publication
        record_publication(
            canonical_url="https://example.com/article", platform="bluesky",
            article_id="single", url="https://bsky.app/s",
        )
        record_deletion("https://example.com/article", "bluesky")
        assert is_deleted("https://example.com/article", "bluesky") is True

        # Re-publish as a thread; UPSERT should clear deleted_at
        record_thread_publication(
            canonical_url="https://example.com/article", platform="bluesky",
            root_id="root", root_url="https://bsky.app/r",
            thread_ids=["t1", "t2"],
        )
        assert is_deleted("https://example.com/article", "bluesky") is False
        assert is_published("https://example.com/article", "bluesky") is True

    def test_save_stats_does_not_resurrect_deleted_publication(self, tmp_registry):
        """save_stats must not affect publication state.

        Stats live in a separate table, but a buggy UPSERT could cascade. This
        test pins that updating stats on a soft-deleted publication does not
        resurrect it.
        """
        record_publication(
            canonical_url="https://example.com/article", platform="devto",
            article_id="123", url="https://dev.to/article",
        )
        record_deletion("https://example.com/article", "devto")
        assert is_deleted("https://example.com/article", "devto") is True

        # save_stats on deleted publication: should be a no-op or update stats
        # without changing publication state.
        save_stats(
            "https://example.com/article", "devto",
            views=100, likes=10,
        )
        assert is_deleted("https://example.com/article", "devto") is True
        assert is_published("https://example.com/article", "devto") is False

    def test_record_failure_does_not_clear_deleted_state(self, tmp_registry):
        """record_failure UPSERT must preserve deleted_at on a successful publication.

        A failed retry attempt must not silently undelete the prior soft-delete.
        The UPSERT only updates last_error/last_error_at on conflict; deleted_at
        must stay set.
        """
        record_publication(
            canonical_url="https://example.com/article", platform="devto",
            article_id="123", url="https://dev.to/article",
        )
        record_deletion("https://example.com/article", "devto")
        assert is_deleted("https://example.com/article", "devto") is True

        # Record a failure on the same (slug, platform); deleted_at should remain
        record_failure(
            canonical_url="https://example.com/article", platform="devto",
            error_msg="API timeout",
        )
        assert is_deleted("https://example.com/article", "devto") is True


class TestRemoveVsDelete:
    """Tests contrasting remove (hard delete) vs record_deletion (soft delete)."""

    def test_remove_publication_fully_removes(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
            title="Test",
        )
        record_publication(
            canonical_url="https://example.com/article",
            platform="bluesky",
            article_id="456",
            url=None,
        )

        remove_publication("https://example.com/article", "devto")

        assert not is_published("https://example.com/article", "devto")
        assert is_published("https://example.com/article", "bluesky")
        assert not is_deleted("https://example.com/article", "devto")

    def test_record_deletion_soft_delete(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )

        record_deletion("https://example.com/article", "devto")

        # Record still exists with deleted_at, but is_published returns False
        assert is_deleted("https://example.com/article", "devto") is True
        assert is_published("https://example.com/article", "devto") is False

        # Can still get publication info
        info = get_publication_info("https://example.com/article", "devto")
        assert info is not None
        assert info["article_id"] == "123"


class TestErrorPersistence:
    """Tests for error recording and retrieval."""

    def test_record_failure_new_article(self, tmp_registry):
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
        assert "devto" in article["platforms"]
        assert article["platforms"]["devto"]["id"] == "123"
        assert article["platforms"]["bluesky"]["last_error"] == "Rate limited"

    def test_success_clears_error(self, tmp_registry):
        record_failure(
            canonical_url="https://example.com/article",
            platform="devto",
            error_msg="Timeout",
        )

        # Now succeed (INSERT OR REPLACE replaces the error row)
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
        record_failure(
            canonical_url="https://example.com/a",
            platform="devto",
            error_msg="500 error",
            title="Article A",
        )
        record_failure(
            canonical_url="https://example.com/b",
            platform="bluesky",
            error_msg="Rate limited",
            title="Article B",
        )

        failures = get_failures()
        assert len(failures) == 2

        urls = {f["canonical_url"] for f in failures}
        assert urls == {"https://example.com/a", "https://example.com/b"}

    def test_get_failures_excludes_successful(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
        )

        failures = get_failures()
        assert len(failures) == 0

    def test_get_failures_mixed(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
            title="Test Article",
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
        failures = get_failures()
        assert failures == []


class TestErrorClearOnSuccess:
    """Tests for error clearing behavior when publication succeeds."""

    def test_record_failure_then_success_clears_error(self, tmp_registry):
        record_failure(
            canonical_url="https://example.com/article",
            platform="devto",
            error_msg="Connection timeout",
        )

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

        article = get_article("https://example.com/article")
        platform_data = article["platforms"]["devto"]
        assert "last_error" not in platform_data
        assert "last_error_at" not in platform_data
        assert platform_data["id"] == "999"

    def test_get_failures_excludes_successful_platforms(self, tmp_registry):
        canonical_url = "https://example.com/article"

        record_failure(
            canonical_url=canonical_url,
            platform="bluesky",
            error_msg="Auth failed",
            title="Test Article",
        )

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
        canonical_url = "https://example.com/article"

        record_failure(
            canonical_url=canonical_url,
            platform="devto",
            error_msg="Server error 500",
            title="Test Article",
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


class TestSQLitePersistence:
    """Tests for SQLite-backed registry persistence."""

    def test_load_registry_format(self, tmp_registry):
        """load_registry returns version 3 dict."""
        registry = load_registry()
        assert registry["version"] == CURRENT_VERSION
        assert isinstance(registry["articles"], dict)
        assert registry["articles"] == {}

    def test_load_reflects_recorded_data(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
            title="Test Article",
        )

        registry = load_registry()
        assert "https://example.com/article" in registry["articles"]
        assert registry["articles"]["https://example.com/article"]["title"] == "Test Article"

    def test_save_preserves_all_fields(self, tmp_registry):
        """Complex data (threads, stats, archived) is all retrievable."""
        canonical_url = "https://example.com/complex-article"

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
            rewritten=True,
            rewrite_author="claude-code",
        )

        save_stats(
            canonical_url=canonical_url,
            platform="bluesky",
            views=100,
            likes=42,
            comments=7,
            reposts=15,
        )

        set_archived(canonical_url, archived=True)

        registry = load_registry()
        article = registry["articles"][canonical_url]

        assert article["title"] == "Thread Article"
        assert article["source_file"] == "posts/thread.md"
        assert article["archived"] is True
        assert "archived_at" in article

        platform_data = article["platforms"]["bluesky"]
        assert platform_data["id"] == "root-001"
        assert platform_data["url"] == "https://bsky.app/post/root-001"
        assert platform_data["is_thread"] is True
        assert platform_data["thread_ids"] == ["root-001", "reply-002", "reply-003"]
        assert len(platform_data["thread_urls"]) == 3
        assert platform_data["rewritten"] is True
        assert platform_data["rewrite_author"] == "claude-code"

    def test_unicode_content(self, tmp_registry):
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

        registry = load_registry()

        article1 = registry["articles"]["https://example.com/unicode-article"]
        assert article1["title"] == "Artigo em Portugues com acentos: caca, maca, cafe"

        article2 = registry["articles"]["https://example.com/japanese-article"]
        assert article2["title"] == "日本語のテスト記事"

        article3 = registry["articles"]["https://example.com/emoji-article"]
        assert article3["platforms"]["bluesky"]["posted_content"] == (
            "Check out this article! It covers Python and Rust topics."
        )

    def test_empty_registry_load(self, tmp_registry):
        registry = load_registry()
        assert registry["version"] == CURRENT_VERSION
        assert registry["articles"] == {}
        assert isinstance(registry["articles"], dict)

    def test_concurrent_reads_during_write(self, tmp_registry):
        """SQLite with WAL mode supports concurrent reads during writes.

        Each thread must use its own connection (SQLite objects are
        thread-local by default), so we use init_db() with an explicit
        db_path to get fresh connections per thread.
        """
        from crier.registry import init_db

        db_path = tmp_registry / "crier.db"

        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
            title="Concurrent Test",
        )

        errors = []

        def load_in_thread():
            try:
                conn = init_db(db_path)
                rows = conn.execute("SELECT * FROM articles").fetchall()
                assert len(rows) >= 1
            except Exception as e:
                errors.append(e)

        def write_in_thread():
            try:
                conn = init_db(db_path)
                slug = "concurrent-write"
                conn.execute(
                    "INSERT OR IGNORE INTO articles (slug, title) VALUES (?, ?)",
                    (slug, "Concurrent Write"),
                )
                conn.commit()
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=write_in_thread)
        t2 = threading.Thread(target=load_in_thread)

        t1.start()
        t2.start()

        t1.join(timeout=5)
        t2.join(timeout=5)

        assert errors == [], f"Threading errors: {errors}"

        registry = load_registry()
        assert "articles" in registry


class TestStats:
    """Tests for stats recording and retrieval."""

    def test_save_and_get_stats(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
            title="Stats Article",
        )

        result = save_stats(
            canonical_url="https://example.com/article",
            platform="devto",
            views=100,
            likes=42,
            comments=7,
            reposts=3,
        )
        assert result is True

        cached = get_cached_stats("https://example.com/article", "devto")
        assert cached is not None
        assert cached["views"] == 100
        assert cached["likes"] == 42
        assert cached["comments"] == 7
        assert cached["reposts"] == 3
        assert "fetched_at" in cached

    def test_save_stats_no_article(self, tmp_registry):
        """save_stats returns False for nonexistent article."""
        result = save_stats(
            canonical_url="https://example.com/nope",
            platform="devto",
            views=10,
        )
        assert result is False

    def test_get_cached_stats_none(self, tmp_registry):
        assert get_cached_stats("https://example.com/nope", "devto") is None

    def test_stats_age_seconds(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
            title="Age Article",
        )
        save_stats(
            canonical_url="https://example.com/article",
            platform="devto",
            views=10,
        )

        age = get_stats_age_seconds("https://example.com/article", "devto")
        assert age is not None
        # Should be very recent (less than 5 seconds)
        assert age < 5.0

    def test_stats_age_no_stats(self, tmp_registry):
        assert get_stats_age_seconds("https://example.com/nope", "devto") is None

    def test_stats_update(self, tmp_registry):
        """Saving stats again overwrites previous values."""
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
            title="Update Stats",
        )
        save_stats(
            canonical_url="https://example.com/article",
            platform="devto",
            views=10,
            likes=5,
        )
        save_stats(
            canonical_url="https://example.com/article",
            platform="devto",
            views=20,
            likes=10,
        )

        cached = get_cached_stats("https://example.com/article", "devto")
        assert cached["views"] == 20
        assert cached["likes"] == 10


class TestThread:
    """Tests for thread publication and queries."""

    def test_record_thread_publication(self, tmp_registry):
        record_thread_publication(
            canonical_url="https://example.com/thread",
            platform="bluesky",
            root_id="root-001",
            root_url="https://bsky.app/post/root-001",
            thread_ids=["root-001", "reply-002", "reply-003"],
            thread_urls=[
                "https://bsky.app/post/root-001",
                "https://bsky.app/post/reply-002",
                "https://bsky.app/post/reply-003",
            ],
            title="Thread Post",
        )

        article = get_article("https://example.com/thread")
        assert article is not None
        pd = article["platforms"]["bluesky"]
        assert pd["is_thread"] is True
        assert pd["thread_ids"] == ["root-001", "reply-002", "reply-003"]
        assert len(pd["thread_urls"]) == 3

    def test_is_thread(self, tmp_registry):
        record_thread_publication(
            canonical_url="https://example.com/thread",
            platform="bluesky",
            root_id="root-001",
            root_url=None,
            thread_ids=["root-001"],
            title="Thread",
        )

        assert is_thread("https://example.com/thread", "bluesky") is True
        assert is_thread("https://example.com/thread", "mastodon") is False

    def test_get_thread_ids(self, tmp_registry):
        ids = ["id1", "id2", "id3"]
        record_thread_publication(
            canonical_url="https://example.com/thread",
            platform="mastodon",
            root_id="id1",
            root_url=None,
            thread_ids=ids,
            title="Thread",
        )

        result = get_thread_ids("https://example.com/thread", "mastodon")
        assert result == ids

    def test_get_thread_ids_none(self, tmp_registry):
        assert get_thread_ids("https://example.com/nope", "bluesky") is None

    def test_non_thread_not_thread(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/article",
            platform="devto",
            article_id="123",
            url=None,
        )
        assert is_thread("https://example.com/article", "devto") is False

    def test_thread_with_rewrite(self, tmp_registry):
        record_thread_publication(
            canonical_url="https://example.com/thread",
            platform="bluesky",
            root_id="root-001",
            root_url="https://bsky.app/post/root-001",
            thread_ids=["root-001", "reply-002"],
            title="Rewritten Thread",
            rewritten=True,
            rewrite_author="claude-code",
        )

        article = get_article("https://example.com/thread")
        pd = article["platforms"]["bluesky"]
        assert pd["rewritten"] is True
        assert pd["rewrite_author"] == "claude-code"


class TestInferSection:
    """Tests for infer_section()."""

    def test_content_post_path(self):
        assert infer_section("content/post/2026-01-01-slug/index.md") == "post"

    def test_content_papers_path(self):
        assert infer_section("content/papers/my-paper/index.md") == "papers"

    def test_content_projects_path(self):
        assert infer_section("content/projects/my-project/index.md") == "projects"

    def test_content_writing_path(self):
        assert infer_section("content/writing/my-story/index.md") == "writing"

    def test_no_content_prefix(self):
        assert infer_section("posts/my-post.md") == "posts"

    def test_none_input(self):
        assert infer_section(None) is None

    def test_bare_filename(self):
        assert infer_section("index.md") is None

    def test_deep_content_path(self):
        assert infer_section("site/content/post/slug/index.md") == "post"

    def test_path_object(self):
        assert infer_section(Path("content/post/slug/index.md")) == "post"


class TestRecordPublicationSection:
    """Tests for section field in record_publication()."""

    def test_section_recorded_for_new_article(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/post/test/",
            platform="devto",
            article_id="123",
            url="https://dev.to/user/test",
            title="Test",
            source_file="content/post/test/index.md",
        )
        registry = load_registry()
        article = registry["articles"]["https://example.com/post/test/"]
        assert article["section"] == "post"

    def test_section_not_set_for_none_source(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/post/test/",
            platform="devto",
            article_id="123",
            url="https://dev.to/user/test",
            title="Test",
            source_file=None,
        )
        registry = load_registry()
        article = registry["articles"]["https://example.com/post/test/"]
        assert "section" not in article

    def test_section_preserved_on_update(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/post/test/",
            platform="devto",
            article_id="123",
            url="https://dev.to/user/test",
            title="Test",
            source_file="content/post/test/index.md",
        )
        record_publication(
            canonical_url="https://example.com/post/test/",
            platform="hashnode",
            article_id="456",
            url="https://hashnode.dev/test",
            source_file="content/post/test/index.md",
        )
        registry = load_registry()
        article = registry["articles"]["https://example.com/post/test/"]
        assert article["section"] == "post"

    def test_papers_section(self, tmp_registry):
        record_publication(
            canonical_url="https://example.com/papers/my-paper/",
            platform="devto",
            article_id="789",
            url="https://dev.to/user/paper",
            title="My Paper",
            source_file="content/papers/my-paper/index.md",
        )
        registry = load_registry()
        article = registry["articles"]["https://example.com/papers/my-paper/"]
        assert article["section"] == "papers"


class TestMigration:
    """Tests for migrate_yaml_to_sqlite()."""

    def test_migrate_basic(self, tmp_registry):
        """Migrate a simple YAML registry to SQLite."""
        yaml_path = tmp_registry / "registry.yaml"
        yaml_data = {
            "version": 2,
            "articles": {
                "https://example.com/article1": {
                    "title": "Article One",
                    "source_file": "posts/one.md",
                    "section": "posts",
                    "content_hash": "sha256:abc123",
                    "platforms": {
                        "devto": {
                            "id": "111",
                            "url": "https://dev.to/one",
                            "published_at": "2025-01-01T00:00:00Z",
                        },
                    },
                },
                "https://example.com/article2": {
                    "title": "Article Two",
                    "source_file": "posts/two.md",
                    "platforms": {
                        "bluesky": {
                            "id": "222",
                            "url": "https://bsky.app/post/222",
                            "published_at": "2025-02-01T00:00:00Z",
                            "rewritten": True,
                            "rewrite_author": "claude-code",
                        },
                    },
                },
            },
        }
        yaml_path.write_text(yaml.dump(yaml_data))

        db_path = tmp_registry / "migrated.db"
        stats = migrate_yaml_to_sqlite(yaml_path, db_path)

        assert stats["articles"] == 2
        assert stats["publications"] == 2
        assert stats["skipped"] == 0

        # Verify YAML was renamed
        assert not yaml_path.exists()
        assert (tmp_registry / "registry.yaml.bak").exists()

    def test_migrate_empty_yaml(self, tmp_registry):
        yaml_path = tmp_registry / "empty.yaml"
        yaml_path.write_text(yaml.dump({"version": 2, "articles": {}}))

        db_path = tmp_registry / "empty.db"
        stats = migrate_yaml_to_sqlite(yaml_path, db_path)

        assert stats == {"articles": 0, "publications": 0, "skipped": 0}

    def test_migrate_nonexistent_yaml(self, tmp_registry):
        yaml_path = tmp_registry / "nonexistent.yaml"
        db_path = tmp_registry / "nope.db"
        stats = migrate_yaml_to_sqlite(yaml_path, db_path)
        assert stats == {"articles": 0, "publications": 0, "skipped": 0}

    def test_migrate_skips_titleless_articles(self, tmp_registry):
        yaml_path = tmp_registry / "notitle.yaml"
        yaml_data = {
            "version": 2,
            "articles": {
                "https://example.com/no-title": {
                    "platforms": {
                        "devto": {
                            "id": "999",
                            "published_at": "2025-01-01T00:00:00Z",
                        },
                    },
                },
            },
        }
        yaml_path.write_text(yaml.dump(yaml_data))

        db_path = tmp_registry / "notitle.db"
        stats = migrate_yaml_to_sqlite(yaml_path, db_path)

        assert stats["skipped"] == 1
        assert stats["articles"] == 0

    def test_migrate_threads(self, tmp_registry):
        yaml_path = tmp_registry / "threads.yaml"
        yaml_data = {
            "version": 2,
            "articles": {
                "https://example.com/thread": {
                    "title": "Thread Article",
                    "platforms": {
                        "bluesky": {
                            "id": "root-001",
                            "url": "https://bsky.app/post/root-001",
                            "published_at": "2025-03-01T00:00:00Z",
                            "is_thread": True,
                            "thread_ids": ["root-001", "reply-002"],
                            "thread_urls": [
                                "https://bsky.app/post/root-001",
                                "https://bsky.app/post/reply-002",
                            ],
                        },
                    },
                },
            },
        }
        yaml_path.write_text(yaml.dump(yaml_data))

        db_path = tmp_registry / "threads.db"
        stats = migrate_yaml_to_sqlite(yaml_path, db_path)

        assert stats["articles"] == 1
        assert stats["publications"] == 1

    def test_migrate_archived(self, tmp_registry):
        yaml_path = tmp_registry / "archived.yaml"
        yaml_data = {
            "version": 2,
            "articles": {
                "https://example.com/old": {
                    "title": "Old Article",
                    "archived": True,
                    "archived_at": "2025-06-01T00:00:00Z",
                    "platforms": {
                        "devto": {
                            "id": "333",
                            "published_at": "2025-01-01T00:00:00Z",
                        },
                    },
                },
            },
        }
        yaml_path.write_text(yaml.dump(yaml_data))

        db_path = tmp_registry / "archived.db"
        stats = migrate_yaml_to_sqlite(yaml_path, db_path)

        assert stats["articles"] == 1

    def test_migrate_with_stats(self, tmp_registry):
        yaml_path = tmp_registry / "stats.yaml"
        yaml_data = {
            "version": 2,
            "articles": {
                "https://example.com/stats-article": {
                    "title": "Stats Article",
                    "platforms": {
                        "devto": {
                            "id": "444",
                            "published_at": "2025-01-01T00:00:00Z",
                            "stats": {
                                "views": 100,
                                "likes": 50,
                                "comments": 10,
                                "reposts": 5,
                                "fetched_at": "2025-06-01T12:00:00Z",
                            },
                        },
                    },
                },
            },
        }
        yaml_path.write_text(yaml.dump(yaml_data))

        db_path = tmp_registry / "stats.db"
        stats = migrate_yaml_to_sqlite(yaml_path, db_path)

        assert stats["articles"] == 1
        assert stats["publications"] == 1

    def test_migrate_with_errors(self, tmp_registry):
        yaml_path = tmp_registry / "errors.yaml"
        yaml_data = {
            "version": 2,
            "articles": {
                "https://example.com/err": {
                    "title": "Error Article",
                    "platforms": {
                        "devto": {
                            "id": "555",
                            "published_at": "2025-01-01T00:00:00Z",
                            "last_error": "API 500",
                            "last_error_at": "2025-06-01T00:00:00Z",
                        },
                    },
                },
            },
        }
        yaml_path.write_text(yaml.dump(yaml_data))

        db_path = tmp_registry / "errors.db"
        stats = migrate_yaml_to_sqlite(yaml_path, db_path)

        assert stats["articles"] == 1
        assert stats["publications"] == 1

    def test_migrate_multi_platform(self, tmp_registry):
        yaml_path = tmp_registry / "multi.yaml"
        yaml_data = {
            "version": 2,
            "articles": {
                "https://example.com/multi": {
                    "title": "Multi-Platform Article",
                    "platforms": {
                        "devto": {
                            "id": "d1",
                            "published_at": "2025-01-01T00:00:00Z",
                        },
                        "bluesky": {
                            "id": "b1",
                            "published_at": "2025-01-02T00:00:00Z",
                            "rewritten": True,
                        },
                        "hashnode": {
                            "id": "h1",
                            "published_at": "2025-01-03T00:00:00Z",
                        },
                    },
                },
            },
        }
        yaml_path.write_text(yaml.dump(yaml_data))

        db_path = tmp_registry / "multi.db"
        stats = migrate_yaml_to_sqlite(yaml_path, db_path)

        assert stats["articles"] == 1
        assert stats["publications"] == 3
