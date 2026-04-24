"""Tests for crier MCP server tools."""

import time

import pytest
import yaml

from crier.mcp_server import (
    _consume_token,
    _create_token,
    _pending_ops,
    crier_archive,
    crier_article,
    crier_check,
    crier_delete,
    crier_doctor,
    crier_failures,
    crier_list_remote,
    crier_missing,
    crier_publications,
    crier_publish,
    crier_query,
    crier_record,
    crier_search,
    crier_sql,
    crier_stats,
    crier_stats_refresh,
    crier_summary,
)
from crier.registry import (
    init_db,
    record_failure,
    record_publication,
    reset_connection,
    save_stats,
)


@pytest.fixture
def mcp_registry(tmp_path, monkeypatch):
    """Set up a fresh SQLite registry for MCP tests."""
    db_path = tmp_path / "crier.db"
    monkeypatch.setenv("CRIER_DB", str(db_path))

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"
    config_file.write_text(yaml.dump({
        "site_root": str(tmp_path),
        "site_base_url": "https://example.com",
        "content_paths": ["content/post"],
        "platforms": {
            "devto": {"api_key": "test_devto_key"},
            "bluesky": {"api_key": "handle.bsky.social:test-password"},
        },
    }))
    monkeypatch.setenv("CRIER_CONFIG", str(config_file))

    reset_connection()
    init_db(db_path)

    # Clean any stale confirmation tokens
    _pending_ops.clear()

    yield tmp_path

    reset_connection()


def _seed_articles(n=3):
    """Seed the registry with test articles."""
    for i in range(n):
        record_publication(
            canonical_url=f"https://example.com/post/{i}/",
            platform="devto",
            article_id=str(1000 + i),
            url=f"https://dev.to/user/post-{i}",
            title=f"Post {i}",
            source_file=f"content/post/{i}/index.md",
        )
    for i in range(min(2, n)):
        record_publication(
            canonical_url=f"https://example.com/post/{i}/",
            platform="bluesky",
            article_id=f"at://post-{i}",
            url=f"https://bsky.app/post/{i}",
            title=f"Post {i}",
            rewritten=True,
            rewrite_author="claude-code",
            posted_content=f"Short version of post {i}",
        )


# ============================================================================
# Confirmation token tests
# ============================================================================


class TestConfirmationTokens:
    def test_create_and_consume(self, mcp_registry):
        token = _create_token("test_op", {"key": "value"})
        result = _consume_token(token, "test_op")
        assert result is not None
        assert result["key"] == "value"

    def test_consume_wrong_operation(self, mcp_registry):
        token = _create_token("publish", {"x": 1})
        result = _consume_token(token, "delete")
        assert result is None

    def test_consume_twice_fails(self, mcp_registry):
        token = _create_token("test_op", {"x": 1})
        _consume_token(token, "test_op")
        assert _consume_token(token, "test_op") is None

    def test_expired_token(self, mcp_registry):
        token = _create_token("test_op", {"x": 1})
        # Manually expire it
        _pending_ops[token]["created_at"] = time.time() - 400
        assert _consume_token(token, "test_op") is None

    def test_invalid_token(self, mcp_registry):
        assert _consume_token("bogus-token", "test_op") is None


# ============================================================================
# Registry tool tests (updated for dict returns)
# ============================================================================


class TestCrierQuery:
    def test_query_all(self, mcp_registry):
        _seed_articles()
        result = crier_query()
        assert result["count"] == 3
        assert all("slug" in r for r in result["articles"])

    def test_query_by_section(self, mcp_registry):
        _seed_articles()
        result = crier_query(section="post")
        assert result["count"] == 3

    def test_query_by_platform(self, mcp_registry):
        _seed_articles()
        result = crier_query(platform="bluesky")
        assert result["count"] == 2

    def test_query_empty(self, mcp_registry):
        result = crier_query()
        assert result["count"] == 0

    def test_query_with_limit(self, mcp_registry):
        _seed_articles(5)
        result = crier_query(limit=2)
        assert result["count"] == 2

    def test_query_invalid_platform(self, mcp_registry):
        result = crier_query(platform="nonexistent")
        assert "error" in result


class TestCrierMissing:
    def test_missing_from_platform(self, mcp_registry):
        _seed_articles()
        result = crier_missing(platforms=["bluesky"])
        assert result["count"] == 1
        assert "bluesky" in result["articles"][0]["missing_platforms"]

    def test_missing_from_multiple(self, mcp_registry):
        _seed_articles()
        result = crier_missing(platforms=["mastodon"])
        assert result["count"] == 3

    def test_nothing_missing(self, mcp_registry):
        _seed_articles()
        result = crier_missing(platforms=["devto"])
        assert result["count"] == 0

    def test_invalid_platform(self, mcp_registry):
        result = crier_missing(platforms=["nonexistent"])
        assert "error" in result


class TestCrierArticle:
    def test_by_canonical_url(self, mcp_registry):
        _seed_articles()
        result = crier_article("https://example.com/post/0/")
        assert result["title"] == "Post 0"
        assert "devto" in result["platforms"]
        assert "bluesky" in result["platforms"]

    def test_by_slug(self, mcp_registry):
        _seed_articles()
        result = crier_article("post-0")
        assert result["title"] == "Post 0"

    def test_not_found(self, mcp_registry):
        result = crier_article("nonexistent")
        assert "error" in result

    def test_by_file(self, mcp_registry):
        _seed_articles()
        result = crier_article("content/post/0/index.md")
        assert result["title"] == "Post 0"


class TestCrierPublications:
    def test_list_platform(self, mcp_registry):
        _seed_articles()
        result = crier_publications("devto")
        assert result["count"] == 3

    def test_empty_platform(self, mcp_registry):
        _seed_articles()
        result = crier_publications("mastodon")
        assert result["count"] == 0

    def test_invalid_platform(self, mcp_registry):
        result = crier_publications("nonexistent")
        assert "error" in result


class TestCrierRecord:
    def test_record_new(self, mcp_registry):
        result = crier_record(
            title="New Post", platform="devto", platform_id="99",
            url="https://dev.to/new", canonical_url="https://example.com/new/",
        )
        assert result["success"] is True

        article = crier_article("https://example.com/new/")
        assert article["title"] == "New Post"
        assert "devto" in article["platforms"]


class TestCrierFailures:
    def test_no_failures(self, mcp_registry):
        result = crier_failures()
        assert result["count"] == 0

    def test_with_failures(self, mcp_registry):
        _seed_articles()
        record_failure("https://example.com/post/0/", "hashnode", "API timeout")
        result = crier_failures()
        assert result["count"] == 1
        assert result["failures"][0]["platform"] == "hashnode"
        assert "timeout" in result["failures"][0]["error"]


class TestCrierStats:
    def test_stats_for_article(self, mcp_registry):
        _seed_articles()
        save_stats("https://example.com/post/0/", "devto", views=100, likes=10)
        result = crier_stats("post-0", "devto")
        assert result["stats"]["views"] == 100

    def test_stats_not_found(self, mcp_registry):
        result = crier_stats("nonexistent")
        assert "error" in result


class TestCrierSql:
    def test_select_articles(self, mcp_registry):
        _seed_articles()
        result = crier_sql("SELECT slug, title FROM articles")
        assert result["count"] == 3

    def test_select_with_join(self, mcp_registry):
        _seed_articles()
        result = crier_sql(
            "SELECT a.title, p.platform FROM articles a "
            "JOIN publications p ON a.slug = p.slug"
        )
        assert result["count"] == 5

    def test_non_select_is_safe(self, mcp_registry):
        """Non-SELECT queries execute inside ROLLBACK, so no data modified."""
        _seed_articles()
        crier_sql("DELETE FROM articles")
        result = crier_sql("SELECT COUNT(*) as n FROM articles")
        assert result["rows"][0]["n"] == 3

    def test_bad_query(self, mcp_registry):
        result = crier_sql("SELECT * FROM nonexistent_table")
        assert "error" in result


class TestCrierSummary:
    def test_summary(self, mcp_registry):
        _seed_articles()
        result = crier_summary()
        assert result["total_articles"] == 3
        assert result["by_platform"]["devto"] == 3
        assert result["by_platform"]["bluesky"] == 2
        assert result["unposted"] == 0

    def test_summary_empty(self, mcp_registry):
        result = crier_summary()
        assert result["total_articles"] == 0
        assert result["unposted"] == 0


# ============================================================================
# Content tool tests
# ============================================================================


class TestCrierSearch:
    def test_search_finds_files(self, mcp_registry):
        """Search finds markdown files in content_paths."""
        content_dir = mcp_registry / "content" / "post" / "test-article"
        content_dir.mkdir(parents=True)
        (content_dir / "index.md").write_text(
            "---\ntitle: Test Article\ndate: 2026-01-01\ntags: [python]\n---\nBody."
        )
        result = crier_search()
        assert result["count"] >= 1
        assert any("Test Article" in r["title"] for r in result["results"])

    def test_search_with_tag_filter(self, mcp_registry):
        content_dir = mcp_registry / "content" / "post" / "tagged"
        content_dir.mkdir(parents=True)
        (content_dir / "index.md").write_text(
            "---\ntitle: Tagged Post\ntags: [rust, wasm]\n---\nBody."
        )
        result = crier_search(tags=["rust"])
        assert result["count"] == 1
        result = crier_search(tags=["python"])
        assert result["count"] == 0

    def test_search_empty(self, mcp_registry):
        result = crier_search()
        assert result["count"] == 0


class TestCrierCheck:
    def test_check_valid_file(self, mcp_registry):
        content_dir = mcp_registry / "content" / "post" / "valid"
        content_dir.mkdir(parents=True)
        md = content_dir / "index.md"
        md.write_text(
            "---\ntitle: Valid Post\ndate: 2026-01-01\ntags: [test]\n"
            "description: A test post\n---\n" + " ".join(["word"] * 100)
        )
        result = crier_check(str(md))
        assert result["passed"] is True

    def test_check_file_not_found(self, mcp_registry):
        result = crier_check("/nonexistent/file.md")
        assert "error" in result

    def test_check_invalid_platform(self, mcp_registry):
        md = mcp_registry / "test.md"
        md.write_text("---\ntitle: X\n---\nBody.")
        result = crier_check(str(md), platforms=["nonexistent"])
        assert "error" in result


# ============================================================================
# Action tool tests
# ============================================================================


class TestCrierArchive:
    def test_archive_and_unarchive(self, mcp_registry):
        _seed_articles()
        result = crier_archive("post-0")
        assert result["success"] is True

        result = crier_archive("post-0", archived=False)
        assert result["success"] is True

    def test_archive_not_found(self, mcp_registry):
        result = crier_archive("nonexistent")
        assert "error" in result


class TestCrierDelete:
    def test_delete_requires_confirmation(self, mcp_registry):
        _seed_articles()
        result = crier_delete("post-0", platform="devto")
        assert result["confirmation_required"] is True
        assert "confirmation_token" in result

    def test_delete_invalid_token(self, mcp_registry):
        _seed_articles()
        result = crier_delete("post-0", platform="devto", confirmation_token="bogus")
        assert "error" in result

    def test_delete_not_found(self, mcp_registry):
        result = crier_delete("nonexistent", platform="devto")
        assert "error" in result

    def test_delete_requires_platform_or_all(self, mcp_registry):
        result = crier_delete("post-0")
        assert "error" in result


class TestCrierPublish:
    def test_publish_dry_run(self, mcp_registry):
        """Dry run returns preview without confirmation."""
        content_dir = mcp_registry / "content" / "post" / "new-article"
        content_dir.mkdir(parents=True)
        md = content_dir / "index.md"
        md.write_text("---\ntitle: New Article\n---\nBody content.")

        result = crier_publish(str(md), "devto", dry_run=True)
        assert result["dry_run"] is True
        assert result["preview"]["title"] == "New Article"

    def test_publish_requires_confirmation(self, mcp_registry):
        """Non-dry-run without token returns confirmation request."""
        content_dir = mcp_registry / "content" / "post" / "article"
        content_dir.mkdir(parents=True)
        md = content_dir / "index.md"
        md.write_text("---\ntitle: Article\n---\nBody.")

        result = crier_publish(str(md), "devto")
        assert result["confirmation_required"] is True
        assert "confirmation_token" in result

    def test_publish_file_not_found(self, mcp_registry):
        result = crier_publish("/nonexistent.md", "devto")
        assert "error" in result

    def test_publish_invalid_platform(self, mcp_registry):
        md = mcp_registry / "test.md"
        md.write_text("---\ntitle: X\n---\nBody.")
        result = crier_publish(str(md), "nonexistent")
        assert "error" in result

    def test_publish_empty_file_path_rejected(self, mcp_registry):
        """Empty file path must be rejected, not resolved to project root."""
        result = crier_publish("", "devto")
        assert "error" in result
        assert "File not found" in result["error"]

    def test_publish_step2_executes_with_mocked_api(self, mcp_registry, monkeypatch):
        """Full two-step flow: token from step 1, execute in step 2 with mocked API."""
        from unittest.mock import patch
        from crier.platforms.base import PublishResult

        content_dir = mcp_registry / "content" / "post" / "real-article"
        content_dir.mkdir(parents=True)
        md = content_dir / "index.md"
        md.write_text("---\ntitle: Real Article\ncanonical_url: https://ex.com/real/\n---\nBody.")

        # Step 1: get token
        step1 = crier_publish(str(md), "devto")
        token = step1["confirmation_token"]

        # Mock devto.publish so step 2 doesn't hit the API
        with patch("crier.platforms.devto.DevTo.publish") as mock_pub:
            mock_pub.return_value = PublishResult(
                success=True, platform="devto",
                article_id="42", url="https://dev.to/u/real-42",
            )
            step2 = crier_publish(str(md), "devto", confirmation_token=token)

        assert step2["success"] is True
        assert step2["article_id"] == "42"
        mock_pub.assert_called_once()
        # The Article passed to publish should have the full body (no rewrite)
        article_arg = mock_pub.call_args[0][0]
        assert article_arg.title == "Real Article"
        assert article_arg.is_rewrite is False

    def test_publish_step2_applies_rewrite_from_token(self, mcp_registry):
        """Rewrite passed in step 1 must be applied in step 2 (regression: commit 6a3bfbe)."""
        from unittest.mock import patch
        from crier.platforms.base import PublishResult

        content_dir = mcp_registry / "content" / "post" / "rewrite-test"
        content_dir.mkdir(parents=True)
        md = content_dir / "index.md"
        md.write_text(
            "---\ntitle: Rewrite Test\ncanonical_url: https://ex.com/rw/\n---\n"
            + "X" * 1000  # Long body — would fail short-form limits without rewrite
        )

        short_rewrite = "Short take."

        # Step 1: with rewrite
        step1 = crier_publish(
            str(md), "bluesky",
            rewrite_content=short_rewrite, rewrite_author="test",
        )
        token = step1["confirmation_token"]

        # Step 2: without rewrite args (simulating a caller that only passes the token)
        with patch("crier.platforms.bluesky.Bluesky.publish") as mock_pub:
            mock_pub.return_value = PublishResult(
                success=True, platform="bluesky",
                article_id="bsky-1", url="https://bsky.app/p/1",
            )
            step2 = crier_publish(str(md), "bluesky", confirmation_token=token)

        assert step2["success"] is True
        # The Article passed must have the rewrite, not the long body
        article_arg = mock_pub.call_args[0][0]
        assert article_arg.body == short_rewrite
        assert article_arg.is_rewrite is True

    def test_publish_step2_token_overrides_caller_args(self, mcp_registry):
        """Security: step 2 uses token's file/platform, not caller's args.

        A caller must not be able to publish file B using a token for file A.
        """
        from unittest.mock import patch
        from crier.platforms.base import PublishResult

        # Two different files
        a_dir = mcp_registry / "content" / "post" / "article-a"
        a_dir.mkdir(parents=True)
        a_md = a_dir / "index.md"
        a_md.write_text("---\ntitle: Article A\ncanonical_url: https://ex.com/a/\n---\nA body.")

        b_dir = mcp_registry / "content" / "post" / "article-b"
        b_dir.mkdir(parents=True)
        b_md = b_dir / "index.md"
        b_md.write_text("---\ntitle: Article B\ncanonical_url: https://ex.com/b/\n---\nB body.")

        # Step 1: get token for A
        step1 = crier_publish(str(a_md), "devto")
        token = step1["confirmation_token"]
        assert step1["preview"]["title"] == "Article A"

        # Step 2: caller tries to substitute B
        with patch("crier.platforms.devto.DevTo.publish") as mock_pub:
            mock_pub.return_value = PublishResult(
                success=True, platform="devto",
                article_id="1", url="https://dev.to/x",
            )
            crier_publish(str(b_md), "devto", confirmation_token=token)

        # The article actually published must be A (from token), not B
        article_arg = mock_pub.call_args[0][0]
        assert article_arg.title == "Article A"


class TestCrierDeleteStep2:
    """Full two-step delete flow tests."""

    def test_delete_step2_token_overrides_caller_key(self, mcp_registry):
        """Security: step 2 uses token's key, not caller's args.

        A caller must not be able to delete article B using a token for article A.
        """
        _seed_articles()

        # Step 1: get token for post-0
        step1 = crier_delete("post-0", platform="devto")
        token = step1["confirmation_token"]
        assert step1["preview"]["slug"] == "post-0"

        # Step 2: caller tries to substitute post-1
        result = crier_delete("post-1", platform="devto", confirmation_token=token)

        # The deletion target should be from the token (post-0)
        assert "deleted" in result
        assert all(r["platform"] == "devto" for r in result["deleted"])

        # Verify post-0 marked deleted, post-1 untouched
        from crier.registry import is_deleted
        assert is_deleted("post-0", "devto") is True
        assert is_deleted("post-1", "devto") is False

    def test_delete_already_deleted(self, mcp_registry):
        """Deleting an already-deleted publication returns an error in step 1."""
        _seed_articles()
        from crier.registry import record_deletion
        record_deletion("post-0", "devto")

        result = crier_delete("post-0", platform="devto")
        assert "error" in result
        assert "already deleted" in result["error"].lower()


class TestCrierStatsValidation:
    """crier_stats and crier_stats_refresh should validate platform names."""

    def test_stats_invalid_platform(self, mcp_registry):
        _seed_articles()
        result = crier_stats("post-0", platform="nonexistent")
        assert "error" in result

    def test_stats_refresh_invalid_platform(self, mcp_registry):
        result = crier_stats_refresh(platform="nonexistent")
        assert "error" in result


class TestCrierDoctor:
    def test_doctor_returns_platform_status(self, mcp_registry):
        result = crier_doctor()
        assert "platforms" in result
        assert "total" in result
        assert result["total"] >= 13


class TestCrierListRemote:
    def test_invalid_platform(self, mcp_registry):
        result = crier_list_remote("nonexistent")
        assert "error" in result

    def test_no_api_key(self, mcp_registry):
        result = crier_list_remote("ghost")
        assert "error" in result


class TestCrierStatsRefresh:
    def test_article_not_found(self, mcp_registry):
        result = crier_stats_refresh(key="nonexistent")
        assert "error" in result

    def test_refresh_empty_registry(self, mcp_registry):
        result = crier_stats_refresh()
        assert result["count"] == 0
