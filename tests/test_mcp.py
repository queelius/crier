"""Tests for crier MCP server tools."""

import json

import pytest
import yaml

from crier.mcp_server import (
    crier_article,
    crier_missing,
    crier_publications,
    crier_query,
    crier_record,
    crier_sql,
    crier_stats,
    crier_summary,
)
from crier.registry import (
    init_db,
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
    config_file.write_text(yaml.dump({"site_root": str(tmp_path)}))
    monkeypatch.setenv("CRIER_CONFIG", str(config_file))

    reset_connection()
    init_db(db_path)

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
    # Also publish first two to bluesky
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


class TestCrierQuery:
    def test_query_all(self, mcp_registry):
        _seed_articles()
        result = json.loads(crier_query())
        assert len(result) == 3
        assert all("slug" in r for r in result)

    def test_query_by_section(self, mcp_registry):
        _seed_articles()
        result = json.loads(crier_query(section="post"))
        assert len(result) == 3

    def test_query_by_platform(self, mcp_registry):
        _seed_articles()
        result = json.loads(crier_query(platform="bluesky"))
        assert len(result) == 2

    def test_query_empty(self, mcp_registry):
        result = json.loads(crier_query())
        assert result == []

    def test_query_with_limit(self, mcp_registry):
        _seed_articles(5)
        result = json.loads(crier_query(limit=2))
        assert len(result) == 2


class TestCrierMissing:
    def test_missing_from_platform(self, mcp_registry):
        _seed_articles()
        result = json.loads(crier_missing(platforms=["bluesky"]))
        # Post 2 is not on bluesky
        assert len(result) == 1
        assert "bluesky" in result[0]["missing_platforms"]

    def test_missing_from_multiple(self, mcp_registry):
        _seed_articles()
        result = json.loads(crier_missing(platforms=["mastodon"]))
        # Nothing is on mastodon
        assert len(result) == 3

    def test_nothing_missing(self, mcp_registry):
        _seed_articles()
        result = json.loads(crier_missing(platforms=["devto"]))
        assert result == []


class TestCrierArticle:
    def test_by_canonical_url(self, mcp_registry):
        _seed_articles()
        result = json.loads(crier_article("https://example.com/post/0/"))
        assert result["title"] == "Post 0"
        assert "devto" in result["platforms"]
        assert "bluesky" in result["platforms"]

    def test_by_slug(self, mcp_registry):
        _seed_articles()
        result = json.loads(crier_article("post-0"))
        assert result["title"] == "Post 0"

    def test_not_found(self, mcp_registry):
        result = json.loads(crier_article("nonexistent"))
        assert "error" in result

    def test_by_file(self, mcp_registry):
        _seed_articles()
        result = json.loads(crier_article("content/post/0/index.md"))
        assert result["title"] == "Post 0"


class TestCrierPublications:
    def test_list_platform(self, mcp_registry):
        _seed_articles()
        result = json.loads(crier_publications("devto"))
        assert len(result) == 3
        assert all(r["platform_url"].startswith("https://dev.to/") for r in result)

    def test_empty_platform(self, mcp_registry):
        _seed_articles()
        result = json.loads(crier_publications("mastodon"))
        assert result == []


class TestCrierRecord:
    def test_record_new(self, mcp_registry):
        result = json.loads(crier_record(
            title="New Post",
            platform="devto",
            platform_id="99",
            url="https://dev.to/new",
            canonical_url="https://example.com/new/",
        ))
        assert result["success"] is True

        # Verify it was recorded
        article = json.loads(crier_article("https://example.com/new/"))
        assert article["title"] == "New Post"
        assert "devto" in article["platforms"]


class TestCrierStats:
    def test_stats_for_article(self, mcp_registry):
        _seed_articles()
        save_stats("https://example.com/post/0/", "devto", views=100, likes=10)

        result = json.loads(crier_stats("post-0", "devto"))
        assert result["stats"]["views"] == 100

    def test_stats_not_found(self, mcp_registry):
        result = json.loads(crier_stats("nonexistent"))
        assert "error" in result


class TestCrierSql:
    def test_select_articles(self, mcp_registry):
        _seed_articles()
        result = json.loads(crier_sql("SELECT slug, title FROM articles"))
        assert result["count"] == 3
        assert all("slug" in r for r in result["rows"])

    def test_select_with_join(self, mcp_registry):
        _seed_articles()
        result = json.loads(crier_sql(
            "SELECT a.title, p.platform FROM articles a "
            "JOIN publications p ON a.slug = p.slug"
        ))
        assert result["count"] == 5  # 3 devto + 2 bluesky

    def test_reject_non_select(self, mcp_registry):
        result = json.loads(crier_sql("DELETE FROM articles"))
        assert "error" in result

    def test_bad_query(self, mcp_registry):
        result = json.loads(crier_sql("SELECT * FROM nonexistent_table"))
        assert "error" in result


class TestCrierSummary:
    def test_summary(self, mcp_registry):
        _seed_articles()
        result = json.loads(crier_summary())
        assert result["total_articles"] == 3
        assert result["by_platform"]["devto"] == 3
        assert result["by_platform"]["bluesky"] == 2
        assert result["unposted"] == 0

    def test_summary_empty(self, mcp_registry):
        result = json.loads(crier_summary())
        assert result["total_articles"] == 0
        assert result["unposted"] == 0
