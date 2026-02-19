"""Tests for crier stats functionality."""

import pytest
import yaml
from datetime import datetime, timezone
from unittest.mock import patch

from crier.registry import (
    save_stats,
    get_cached_stats,
    get_stats_age_seconds,
    record_publication,
)
from crier.platforms.base import ArticleStats


@pytest.fixture
def tmp_registry(tmp_path, monkeypatch):
    """Set up a temporary registry directory with isolated config.

    Registry now uses get_site_root() from config, so we point
    CRIER_CONFIG at a temp config with site_root = tmp_path.
    """
    crier_dir = tmp_path / ".crier"
    crier_dir.mkdir()

    # Write a config that points site_root at tmp_path
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"
    config_file.write_text(yaml.dump({"site_root": str(tmp_path)}))
    monkeypatch.setenv("CRIER_CONFIG", str(config_file))

    monkeypatch.chdir(tmp_path)
    return tmp_path


def _setup_isolated_config(tmp_path, monkeypatch):
    """Helper to set up isolated config for CLI tests that use tmp_path directly."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    config_file = config_dir / "config.yaml"
    config_file.write_text(yaml.dump({"site_root": str(tmp_path)}))
    monkeypatch.setenv("CRIER_CONFIG", str(config_file))


class TestArticleStats:
    """Tests for ArticleStats dataclass."""

    def test_create_with_all_fields(self):
        """Create ArticleStats with all fields."""
        stats = ArticleStats(
            views=1000,
            likes=50,
            comments=10,
            reposts=5,
        )
        assert stats.views == 1000
        assert stats.likes == 50
        assert stats.comments == 10
        assert stats.reposts == 5
        assert stats.fetched_at is not None

    def test_create_with_partial_fields(self):
        """Create ArticleStats with only some fields."""
        stats = ArticleStats(likes=25, comments=3)
        assert stats.views is None
        assert stats.likes == 25
        assert stats.comments == 3
        assert stats.reposts is None

    def test_default_fetched_at(self):
        """Default fetched_at is current time."""
        before = datetime.now(timezone.utc)
        stats = ArticleStats()
        after = datetime.now(timezone.utc)

        assert before <= stats.fetched_at <= after


class TestRegistryStats:
    """Tests for registry stats caching functions."""

    def test_save_and_get_stats(self, tmp_registry):
        """Save and retrieve stats from registry."""
        canonical_url = "https://example.com/article"

        # First create a publication
        record_publication(
            canonical_url=canonical_url,
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
            title="Test Article",
        )

        # Save stats
        result = save_stats(
            canonical_url=canonical_url,
            platform="devto",
            views=500,
            likes=25,
            comments=5,
        )
        assert result is True

        # Get cached stats
        stats = get_cached_stats(canonical_url, "devto")
        assert stats is not None
        assert stats["views"] == 500
        assert stats["likes"] == 25
        assert stats["comments"] == 5
        assert stats["reposts"] is None
        assert "fetched_at" in stats

    def test_save_stats_not_found(self, tmp_registry):
        """Saving stats for nonexistent publication returns False."""
        result = save_stats(
            canonical_url="https://nonexistent.com",
            platform="devto",
            views=100,
        )
        assert result is False

    def test_save_stats_wrong_platform(self, tmp_registry):
        """Saving stats for wrong platform returns False."""
        canonical_url = "https://example.com/article"

        # Create publication on devto only
        record_publication(
            canonical_url=canonical_url,
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
        )

        # Try to save stats for bluesky
        result = save_stats(
            canonical_url=canonical_url,
            platform="bluesky",
            likes=10,
        )
        assert result is False

    def test_get_cached_stats_not_found(self, tmp_registry):
        """Getting stats for nonexistent article returns None."""
        stats = get_cached_stats("https://nonexistent.com", "devto")
        assert stats is None

    def test_get_cached_stats_no_stats(self, tmp_registry):
        """Getting stats when none cached returns None."""
        canonical_url = "https://example.com/article"

        record_publication(
            canonical_url=canonical_url,
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
        )

        stats = get_cached_stats(canonical_url, "devto")
        assert stats is None

    def test_stats_age_seconds(self, tmp_registry):
        """Get age of cached stats in seconds."""
        canonical_url = "https://example.com/article"

        record_publication(
            canonical_url=canonical_url,
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
        )

        save_stats(
            canonical_url=canonical_url,
            platform="devto",
            views=100,
        )

        age = get_stats_age_seconds(canonical_url, "devto")
        assert age is not None
        assert age >= 0
        assert age < 5  # Should be very recent

    def test_stats_age_no_stats(self, tmp_registry):
        """Stats age returns None when no stats cached."""
        canonical_url = "https://example.com/article"

        record_publication(
            canonical_url=canonical_url,
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
        )

        age = get_stats_age_seconds(canonical_url, "devto")
        assert age is None


class TestPlatformStats:
    """Tests for platform get_stats implementations."""

    def test_devto_get_stats(self):
        """DevTo get_stats parses response correctly."""
        from crier.platforms.devto import DevTo

        platform = DevTo("fake-api-key")

        with patch.object(platform, "get_article") as mock_get:
            mock_get.return_value = {
                "page_views_count": 1523,
                "public_reactions_count": 47,
                "comments_count": 12,
            }

            stats = platform.get_stats("123")
            assert stats is not None
            assert stats.views == 1523
            assert stats.likes == 47
            assert stats.comments == 12
            assert stats.reposts is None

    def test_devto_get_stats_not_found(self):
        """DevTo get_stats returns None when article not found."""
        from crier.platforms.devto import DevTo

        platform = DevTo("fake-api-key")

        with patch.object(platform, "get_article") as mock_get:
            mock_get.return_value = None
            stats = platform.get_stats("nonexistent")
            assert stats is None

    def test_bluesky_get_stats(self):
        """Bluesky get_stats parses response correctly."""
        from crier.platforms.bluesky import Bluesky

        platform = Bluesky("handle:password")

        with patch.object(platform, "get_article") as mock_get:
            mock_get.return_value = {
                "likeCount": 23,
                "replyCount": 5,
                "repostCount": 8,
            }

            stats = platform.get_stats("at://did:plc:xxx/app.bsky.feed.post/yyy")
            assert stats is not None
            assert stats.views is None  # Bluesky doesn't provide views
            assert stats.likes == 23
            assert stats.comments == 5
            assert stats.reposts == 8

    def test_mastodon_get_stats(self):
        """Mastodon get_stats parses response correctly."""
        from crier.platforms.mastodon import Mastodon

        platform = Mastodon("mastodon.social:token")

        with patch.object(platform, "get_article") as mock_get:
            mock_get.return_value = {
                "favourites_count": 15,
                "replies_count": 3,
                "reblogs_count": 4,
            }

            stats = platform.get_stats("123456")
            assert stats is not None
            assert stats.views is None
            assert stats.likes == 15
            assert stats.comments == 3
            assert stats.reposts == 4

    def test_platform_supports_stats_flag(self):
        """Check supports_stats flag on platforms."""
        from crier.platforms.devto import DevTo
        from crier.platforms.bluesky import Bluesky
        from crier.platforms.mastodon import Mastodon
        from crier.platforms.medium import Medium
        from crier.platforms.twitter import Twitter

        assert DevTo.supports_stats is True
        assert Bluesky.supports_stats is True
        assert Mastodon.supports_stats is True
        assert Medium.supports_stats is False
        assert Twitter.supports_stats is False


class TestStatsCLI:
    """Tests for crier stats CLI command."""

    def test_stats_help(self, tmp_path, monkeypatch):
        """Stats command shows help."""
        from click.testing import CliRunner
        from crier.cli import cli

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["stats", "--help"])

        assert result.exit_code == 0
        assert "Show engagement stats" in result.output

    def test_stats_no_registry(self, tmp_path, monkeypatch):
        """Stats command with no registry."""
        from click.testing import CliRunner
        from crier.cli import cli

        crier_dir = tmp_path / ".crier"
        crier_dir.mkdir()
        _setup_isolated_config(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["stats"])

        assert result.exit_code == 1
        assert "No articles in registry" in result.output

    def test_stats_file_not_in_registry(self, tmp_path, monkeypatch):
        """Stats for file not in registry."""
        from click.testing import CliRunner
        from crier.cli import cli

        crier_dir = tmp_path / ".crier"
        crier_dir.mkdir()
        _setup_isolated_config(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)

        # Create markdown file
        md_file = tmp_path / "article.md"
        md_file.write_text("""---
title: Test Article
canonical_url: https://example.com/test
---

Content here.
""")

        runner = CliRunner()
        result = runner.invoke(cli, ["stats", str(md_file)])

        assert result.exit_code == 1
        assert "Not found in registry" in result.output

    def test_stats_json_output(self, tmp_path, monkeypatch):
        """Stats command with JSON output."""
        import json
        from click.testing import CliRunner
        from crier.cli import cli

        crier_dir = tmp_path / ".crier"
        crier_dir.mkdir()
        _setup_isolated_config(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)

        # Create markdown file
        md_file = tmp_path / "article.md"
        md_file.write_text("""---
title: Test Article
canonical_url: https://example.com/test
---

Content here.
""")

        # Record publication with stats
        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            title="Test Article",
            source_file=str(md_file),
        )

        save_stats(
            canonical_url="https://example.com/test",
            platform="devto",
            views=100,
            likes=10,
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["stats", str(md_file), "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        assert data["title"] == "Test Article"
        assert len(data["platforms"]) == 1
        assert data["platforms"][0]["views"] == 100
        assert data["platforms"][0]["likes"] == 10

    def test_stats_top_filter(self, tmp_path, monkeypatch):
        """Stats command with --top filter."""
        from click.testing import CliRunner
        from crier.cli import cli

        crier_dir = tmp_path / ".crier"
        crier_dir.mkdir()
        _setup_isolated_config(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)

        # Create multiple publications with stats
        for i in range(5):
            canonical_url = f"https://example.com/article{i}"
            record_publication(
                canonical_url=canonical_url,
                platform="devto",
                article_id=str(100 + i),
                url=f"https://dev.to/article{i}",
                title=f"Article {i}",
            )
            save_stats(
                canonical_url=canonical_url,
                platform="devto",
                likes=i * 10,  # 0, 10, 20, 30, 40
            )

        runner = CliRunner()
        result = runner.invoke(cli, ["stats", "--top", "3", "--json"])

        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["success"] is True
        assert len(data["articles"]) == 3
        # Should be sorted by engagement (highest first)
        assert data["articles"][0]["likes"] == 40
        assert data["articles"][1]["likes"] == 30
        assert data["articles"][2]["likes"] == 20


class TestRegistryStatsEdgeCases:
    """Edge case tests for registry stats caching."""

    def test_save_stats_with_all_fields(self, tmp_registry):
        """Save stats including reposts field."""
        canonical_url = "https://example.com/article"

        record_publication(
            canonical_url=canonical_url,
            platform="bluesky",
            article_id="at://...",
            url="https://bsky.app/...",
        )

        result = save_stats(
            canonical_url=canonical_url,
            platform="bluesky",
            views=None,
            likes=42,
            comments=7,
            reposts=15,
        )
        assert result is True

        stats = get_cached_stats(canonical_url, "bluesky")
        assert stats["views"] is None
        assert stats["likes"] == 42
        assert stats["comments"] == 7
        assert stats["reposts"] == 15

    def test_save_stats_overwrites_previous(self, tmp_registry):
        """Saving stats overwrites previous values."""
        canonical_url = "https://example.com/article"

        record_publication(
            canonical_url=canonical_url,
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
        )

        save_stats(canonical_url=canonical_url, platform="devto", views=100)
        save_stats(canonical_url=canonical_url, platform="devto", views=200)

        stats = get_cached_stats(canonical_url, "devto")
        assert stats["views"] == 200

    def test_get_cached_stats_wrong_platform(self, tmp_registry):
        """Getting stats for existing article but wrong platform returns None."""
        canonical_url = "https://example.com/article"

        record_publication(
            canonical_url=canonical_url,
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
        )

        save_stats(canonical_url=canonical_url, platform="devto", views=100)

        stats = get_cached_stats(canonical_url, "bluesky")
        assert stats is None

    def test_stats_age_nonexistent_article(self, tmp_registry):
        """Stats age for nonexistent article returns None."""
        age = get_stats_age_seconds("https://nonexistent.com", "devto")
        assert age is None

    def test_stats_age_nonexistent_platform(self, tmp_registry):
        """Stats age for nonexistent platform returns None."""
        canonical_url = "https://example.com/article"

        record_publication(
            canonical_url=canonical_url,
            platform="devto",
            article_id="123",
            url="https://dev.to/article",
        )

        age = get_stats_age_seconds(canonical_url, "bluesky")
        assert age is None

    def test_multiple_platforms_independent_stats(self, tmp_registry):
        """Stats for different platforms on same article are independent."""
        canonical_url = "https://example.com/article"

        record_publication(canonical_url=canonical_url, platform="devto", article_id="123", url="u1")
        record_publication(canonical_url=canonical_url, platform="bluesky", article_id="456", url="u2")

        save_stats(canonical_url=canonical_url, platform="devto", views=1000, likes=50)
        save_stats(canonical_url=canonical_url, platform="bluesky", likes=25, reposts=10)

        devto_stats = get_cached_stats(canonical_url, "devto")
        bluesky_stats = get_cached_stats(canonical_url, "bluesky")

        assert devto_stats["views"] == 1000
        assert devto_stats["likes"] == 50
        assert bluesky_stats["likes"] == 25
        assert bluesky_stats["reposts"] == 10


class TestPlatformStatsEdgeCases:
    """Edge case tests for platform get_stats implementations."""

    def test_devto_get_stats_partial_data(self):
        """DevTo get_stats handles missing fields."""
        from crier.platforms.devto import DevTo

        platform = DevTo("fake-api-key")

        with patch.object(platform, "get_article") as mock_get:
            mock_get.return_value = {
                "page_views_count": 100,
                # Missing public_reactions_count and comments_count
            }

            stats = platform.get_stats("123")
            assert stats is not None
            assert stats.views == 100
            assert stats.likes is None
            assert stats.comments is None

    def test_bluesky_get_stats_not_found(self):
        """Bluesky get_stats returns None when post not found."""
        from crier.platforms.bluesky import Bluesky

        platform = Bluesky("handle:password")

        with patch.object(platform, "get_article") as mock_get:
            mock_get.return_value = None
            stats = platform.get_stats("at://did:plc:xxx/post/yyy")
            assert stats is None

    def test_mastodon_get_stats_not_found(self):
        """Mastodon get_stats returns None when status not found."""
        from crier.platforms.mastodon import Mastodon

        platform = Mastodon("mastodon.social:token")

        with patch.object(platform, "get_article") as mock_get:
            mock_get.return_value = None
            stats = platform.get_stats("123456")
            assert stats is None

    def test_base_platform_get_stats_default(self):
        """Base Platform.get_stats returns None by default."""
        from crier.platforms.twitter import Twitter

        platform = Twitter("manual")
        stats = platform.get_stats("123")
        assert stats is None

    def test_linkedin_supports_stats_flag(self):
        """LinkedIn supports stats via socialActions API."""
        from crier.platforms.linkedin import LinkedIn

        assert LinkedIn.supports_stats is True

    def test_telegram_supports_stats_flag(self):
        """Telegram does not support stats."""
        from crier.platforms.telegram import Telegram

        assert Telegram.supports_stats is False


class TestStatsCLIEdgeCases:
    """Edge case tests for stats CLI command."""

    def test_stats_help_text(self, tmp_path, monkeypatch):
        """Stats help shows relevant options."""
        from click.testing import CliRunner
        from crier.cli import cli

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["stats", "--help"])

        assert result.exit_code == 0
        assert "--json" in result.output
        assert "--top" in result.output

    def test_stats_with_file_found_in_registry(self, tmp_path, monkeypatch):
        """Stats for file tracked in registry shows platform info."""
        from click.testing import CliRunner
        from crier.cli import cli

        crier_dir = tmp_path / ".crier"
        crier_dir.mkdir()
        _setup_isolated_config(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)

        md_file = tmp_path / "article.md"
        md_file.write_text("---\ntitle: My Article\ncanonical_url: https://example.com/my\n---\nContent.")

        record_publication(
            canonical_url="https://example.com/my",
            platform="devto",
            article_id="42",
            url="https://dev.to/my",
            title="My Article",
            source_file=str(md_file),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["stats", str(md_file)])

        assert result.exit_code == 0
        assert "My Article" in result.output or "devto" in result.output

    def test_stats_json_no_stats_cached(self, tmp_path, monkeypatch):
        """Stats JSON for article with no cached stats returns empty platforms list."""
        import json
        from click.testing import CliRunner
        from crier.cli import cli

        crier_dir = tmp_path / ".crier"
        crier_dir.mkdir()
        _setup_isolated_config(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)

        md_file = tmp_path / "article.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            title="Test",
            source_file=str(md_file),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["stats", str(md_file), "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        # No stats cached and no API key = empty platforms list
        assert isinstance(data["platforms"], list)
        assert data["totals"]["views"] == 0

    def test_stats_json_with_cached_stats(self, tmp_path, monkeypatch):
        """Stats JSON returns cached stats when available."""
        import json
        from click.testing import CliRunner
        from crier.cli import cli

        crier_dir = tmp_path / ".crier"
        crier_dir.mkdir()
        _setup_isolated_config(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)

        md_file = tmp_path / "article.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            title="Test",
            source_file=str(md_file),
        )

        # Pre-populate cache
        save_stats(
            canonical_url="https://example.com/test",
            platform="devto",
            views=500,
            likes=42,
            comments=7,
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["stats", str(md_file), "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        assert len(data["platforms"]) == 1
        assert data["platforms"][0]["platform"] == "devto"
        assert data["platforms"][0]["views"] == 500
        assert data["platforms"][0]["likes"] == 42

    def test_stats_top_with_no_articles(self, tmp_path, monkeypatch):
        """Stats --top with no articles in registry."""
        from click.testing import CliRunner
        from crier.cli import cli

        crier_dir = tmp_path / ".crier"
        crier_dir.mkdir()
        _setup_isolated_config(tmp_path, monkeypatch)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["stats", "--top", "5"])

        assert result.exit_code == 1
        assert "No articles" in result.output
