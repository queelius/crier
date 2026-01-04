"""Tests for crier CLI commands."""

import pytest
import yaml
from pathlib import Path
from click.testing import CliRunner
from unittest.mock import Mock, patch

from crier.cli import cli
from crier import __version__


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_config_and_registry(tmp_path, monkeypatch):
    """Set up mock config and registry for CLI tests."""
    # Config
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"
    config = {
        "platforms": {
            "devto": {"api_key": "test_devto_key"},
            "bluesky": {"api_key": "handle.bsky.social:app-password"},
            "twitter": {"api_key": "manual"},
        },
        "profiles": {
            "blogs": ["devto", "hashnode"],
            "social": ["bluesky", "mastodon"],
        },
        "content_paths": [str(tmp_path / "posts")],
    }
    config_file.write_text(yaml.dump(config))
    monkeypatch.setattr("crier.config.DEFAULT_CONFIG_FILE", config_file)
    monkeypatch.setattr("crier.config.DEFAULT_CONFIG_DIR", config_dir)
    monkeypatch.delenv("CRIER_CONFIG", raising=False)

    # Registry
    registry_dir = tmp_path / ".crier"
    registry_dir.mkdir()
    registry_file = registry_dir / "registry.yaml"
    registry_file.write_text("version: 2\narticles: {}\n")
    monkeypatch.chdir(tmp_path)

    # Create posts directory
    posts_dir = tmp_path / "posts"
    posts_dir.mkdir()

    return {
        "config_file": config_file,
        "registry_dir": registry_dir,
        "posts_dir": posts_dir,
        "tmp_path": tmp_path,
    }


class TestVersionCommand:
    """Tests for --version flag."""

    def test_version(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output


class TestDoctorCommand:
    """Tests for crier doctor command."""

    def test_doctor_no_config(self, runner, tmp_path, monkeypatch):
        """Doctor with no platforms configured."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        monkeypatch.setattr("crier.config.DEFAULT_CONFIG_FILE", config_file)
        monkeypatch.setattr("crier.config.DEFAULT_CONFIG_DIR", config_dir)
        monkeypatch.delenv("CRIER_CONFIG", raising=False)

        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert "No platforms configured" in result.output or "Not configured" in result.output

    def test_doctor_with_manual_mode(self, runner, mock_config_and_registry):
        """Doctor shows manual mode platforms."""
        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert "Manual mode" in result.output or "manual" in result.output.lower()

    def test_doctor_with_configured_platforms(self, runner, mock_config_and_registry):
        """Doctor shows configured platforms."""
        with patch("crier.cli.get_platform") as mock_get:
            # Mock platform that returns empty list
            mock_platform_cls = Mock()
            mock_platform = Mock()
            mock_platform.list_articles.return_value = []
            mock_platform_cls.return_value = mock_platform
            mock_get.return_value = mock_platform_cls

            result = runner.invoke(cli, ["doctor"])
            assert result.exit_code == 0
            assert "devto" in result.output


class TestConfigCommands:
    """Tests for crier config subcommands."""

    def test_config_show(self, runner, mock_config_and_registry):
        """Show current configuration."""
        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        assert "devto" in result.output
        assert "Configured Platforms" in result.output or "platforms" in result.output.lower()

    def test_config_set_api_key(self, runner, mock_config_and_registry):
        """Set a platform API key."""
        result = runner.invoke(cli, ["config", "set", "hashnode.api_key", "new_key_123"])
        assert result.exit_code == 0
        assert "hashnode" in result.output.lower()

    def test_config_set_invalid_key(self, runner, mock_config_and_registry):
        """Set with invalid key format."""
        result = runner.invoke(cli, ["config", "set", "invalid_key", "value"])
        assert "Unknown config key" in result.output or result.exit_code != 0


class TestProfileCommands:
    """Tests for crier config profile subcommands."""

    def test_profile_show_all(self, runner, mock_config_and_registry):
        """Show all profiles."""
        result = runner.invoke(cli, ["config", "profile", "show"])
        assert result.exit_code == 0
        assert "blogs" in result.output
        assert "social" in result.output

    def test_profile_show_specific(self, runner, mock_config_and_registry):
        """Show a specific profile."""
        result = runner.invoke(cli, ["config", "profile", "show", "blogs"])
        assert result.exit_code == 0
        assert "devto" in result.output

    def test_profile_show_nonexistent(self, runner, mock_config_and_registry):
        """Show nonexistent profile."""
        result = runner.invoke(cli, ["config", "profile", "show", "nonexistent"])
        assert "not found" in result.output.lower()

    def test_profile_set(self, runner, mock_config_and_registry):
        """Create a new profile."""
        result = runner.invoke(cli, ["config", "profile", "set", "myprofile", "devto", "bluesky"])
        assert result.exit_code == 0
        assert "myprofile" in result.output

    def test_profile_delete(self, runner, mock_config_and_registry):
        """Delete a profile."""
        result = runner.invoke(cli, ["config", "profile", "delete", "blogs"])
        assert result.exit_code == 0
        assert "deleted" in result.output.lower()


class TestContentCommands:
    """Tests for crier config content subcommands."""

    def test_content_show(self, runner, mock_config_and_registry):
        """Show content paths."""
        result = runner.invoke(cli, ["config", "content", "show"])
        assert result.exit_code == 0
        assert "posts" in result.output

    def test_content_add(self, runner, mock_config_and_registry):
        """Add a content path."""
        result = runner.invoke(cli, ["config", "content", "add", "articles"])
        assert result.exit_code == 0
        assert "Added" in result.output

    def test_content_remove(self, runner, mock_config_and_registry):
        """Remove a content path."""
        # The fixture stores full path, so use that
        posts_path = str(mock_config_and_registry["posts_dir"])
        result = runner.invoke(cli, ["config", "content", "remove", posts_path])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_content_set(self, runner, mock_config_and_registry):
        """Set content paths."""
        result = runner.invoke(cli, ["config", "content", "set", "content", "blog"])
        assert result.exit_code == 0
        assert "content" in result.output


class TestPublishCommand:
    """Tests for crier publish command."""

    def test_publish_no_platform(self, runner, mock_config_and_registry):
        """Publish without specifying platform fails."""
        # Create a test file
        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("""\
---
title: Test Article
canonical_url: https://example.com/test
---

Content here.
""")

        result = runner.invoke(cli, ["publish", str(test_file)])
        assert result.exit_code != 0
        assert "No platform specified" in result.output

    def test_publish_dry_run(self, runner, mock_config_and_registry):
        """Publish with --dry-run shows preview."""
        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("""\
---
title: Test Article
description: A test description
tags: [python, testing]
canonical_url: https://example.com/test
---

Content here.
""")

        result = runner.invoke(cli, ["publish", str(test_file), "--to", "devto", "--dry-run"])
        assert result.exit_code == 0
        assert "Dry Run" in result.output
        assert "Test Article" in result.output
        assert "devto" in result.output

    def test_publish_dry_run_unconfigured_platform(self, runner, mock_config_and_registry):
        """Dry run shows unconfigured platform status."""
        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("""\
---
title: Test Article
canonical_url: https://example.com/test
---

Content.
""")

        result = runner.invoke(cli, ["publish", str(test_file), "--to", "medium", "--dry-run"])
        assert result.exit_code == 0
        assert "Not configured" in result.output

    def test_publish_with_profile(self, runner, mock_config_and_registry):
        """Publish with profile expands platforms."""
        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("""\
---
title: Test Article
canonical_url: https://example.com/test
---

Content.
""")

        result = runner.invoke(cli, ["publish", str(test_file), "--profile", "blogs", "--dry-run"])
        assert result.exit_code == 0
        assert "devto" in result.output
        assert "hashnode" in result.output

    def test_publish_unknown_profile(self, runner, mock_config_and_registry):
        """Publish with unknown profile fails."""
        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("---\ntitle: Test\n---\nContent.")

        result = runner.invoke(cli, ["publish", str(test_file), "--profile", "nonexistent"])
        assert "Unknown profile" in result.output

    @patch("crier.cli.get_platform")
    def test_publish_success(self, mock_get_platform, runner, mock_config_and_registry):
        """Successful publish records to registry."""
        # Mock successful publish
        mock_platform_cls = Mock()
        mock_platform = Mock()
        mock_result = Mock()
        mock_result.success = True
        mock_result.article_id = "12345"
        mock_result.url = "https://dev.to/user/article"
        mock_result.requires_confirmation = False
        mock_result.error = None
        mock_platform.publish.return_value = mock_result
        mock_platform_cls.return_value = mock_platform
        mock_get_platform.return_value = mock_platform_cls

        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("""\
---
title: Test Article
canonical_url: https://example.com/test
---

Content.
""")

        result = runner.invoke(cli, ["publish", str(test_file), "--to", "devto"])
        assert result.exit_code == 0
        assert "Published" in result.output or "succeeded" in result.output.lower()


class TestStatusCommand:
    """Tests for crier status command."""

    def test_status_no_tracked(self, runner, mock_config_and_registry):
        """Status with no tracked posts."""
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "No posts tracked" in result.output

    def test_status_file_not_tracked(self, runner, mock_config_and_registry):
        """Status for untracked file."""
        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("---\ntitle: Test\n---\nContent.")

        result = runner.invoke(cli, ["status", str(test_file)])
        assert result.exit_code == 0
        assert "No publication record" in result.output


class TestAuditCommand:
    """Tests for crier audit command."""

    def test_audit_no_content_paths(self, runner, tmp_path, monkeypatch):
        """Audit with no content paths configured."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text(yaml.dump({"platforms": {"devto": {"api_key": "key"}}}))
        monkeypatch.setattr("crier.config.DEFAULT_CONFIG_FILE", config_file)
        monkeypatch.setattr("crier.config.DEFAULT_CONFIG_DIR", config_dir)
        monkeypatch.delenv("CRIER_CONFIG", raising=False)

        registry_dir = tmp_path / ".crier"
        registry_dir.mkdir()
        (registry_dir / "registry.yaml").write_text("version: 2\narticles: {}\n")
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(cli, ["audit"])
        assert result.exit_code == 0
        assert "No content paths" in result.output or "No content files" in result.output

    def test_audit_no_platforms(self, runner, tmp_path, monkeypatch):
        """Audit with no platforms configured."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text(yaml.dump({"content_paths": ["posts"]}))
        monkeypatch.setattr("crier.config.DEFAULT_CONFIG_FILE", config_file)
        monkeypatch.setattr("crier.config.DEFAULT_CONFIG_DIR", config_dir)
        monkeypatch.delenv("CRIER_CONFIG", raising=False)

        registry_dir = tmp_path / ".crier"
        registry_dir.mkdir()
        (registry_dir / "registry.yaml").write_text("version: 2\narticles: {}\n")
        monkeypatch.chdir(tmp_path)

        posts_dir = tmp_path / "posts"
        posts_dir.mkdir()
        (posts_dir / "test.md").write_text("---\ntitle: Test\n---\nContent.")

        result = runner.invoke(cli, ["audit"])
        assert result.exit_code == 0
        assert "No platforms configured" in result.output

    def test_audit_with_content(self, runner, mock_config_and_registry):
        """Audit shows content status."""
        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("""\
---
title: Test Article
canonical_url: https://example.com/test
---

Content here.
""")

        result = runner.invoke(cli, ["audit"])
        assert result.exit_code == 0
        assert "Audit" in result.output
        assert "test.md" in result.output

    def test_audit_dry_run(self, runner, mock_config_and_registry):
        """Audit with --dry-run shows preview."""
        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("""\
---
title: Test Article
canonical_url: https://example.com/test
---

Content here.
""")

        result = runner.invoke(cli, ["audit", "--publish", "--dry-run"])
        assert result.exit_code == 0
        assert "Dry Run" in result.output


class TestListCommand:
    """Tests for crier list command."""

    def test_list_no_publications(self, runner, mock_config_and_registry):
        """List with no publications."""
        result = runner.invoke(cli, ["list", "devto"])
        assert result.exit_code == 0
        assert "No articles published" in result.output

    @patch("crier.cli.get_platform")
    def test_list_remote(self, mock_get_platform, runner, mock_config_and_registry):
        """List with --remote queries API."""
        mock_platform_cls = Mock()
        mock_platform = Mock()
        mock_platform.list_articles.return_value = [
            {"id": "1", "title": "Article 1", "url": "https://dev.to/article1"},
            {"id": "2", "title": "Article 2", "url": "https://dev.to/article2"},
        ]
        mock_platform_cls.return_value = mock_platform
        mock_get_platform.return_value = mock_platform_cls

        result = runner.invoke(cli, ["list", "devto", "--remote"])
        assert result.exit_code == 0
        assert "Article 1" in result.output

    @patch("crier.cli.get_platform")
    def test_list_remote_json(self, mock_get_platform, runner, mock_config_and_registry):
        """List with --remote --format json."""
        mock_platform_cls = Mock()
        mock_platform = Mock()
        mock_platform.list_articles.return_value = [{"id": "1", "title": "Test"}]
        mock_platform_cls.return_value = mock_platform
        mock_get_platform.return_value = mock_platform_cls

        result = runner.invoke(cli, ["list", "devto", "--remote", "--format", "json"])
        assert result.exit_code == 0
        assert '"id": "1"' in result.output


class TestSkillCommands:
    """Tests for crier skill subcommands."""

    def test_skill_status(self, runner, mock_config_and_registry):
        """Check skill installation status."""
        result = runner.invoke(cli, ["skill", "status"])
        assert result.exit_code == 0
        assert "Skill Status" in result.output

    def test_skill_show(self, runner, mock_config_and_registry):
        """Show skill content."""
        result = runner.invoke(cli, ["skill", "show"])
        assert result.exit_code == 0
        assert "crier" in result.output.lower()

    def test_skill_install(self, runner, mock_config_and_registry, tmp_path, monkeypatch):
        """Install skill."""
        # Mock the skill path to use tmp_path
        skills_dir = tmp_path / ".claude" / "skills"
        monkeypatch.setattr("crier.skill.GLOBAL_SKILLS_DIR", skills_dir)

        result = runner.invoke(cli, ["skill", "install"])
        assert result.exit_code == 0
        assert "Installed" in result.output or "up-to-date" in result.output.lower()

    def test_skill_uninstall_not_installed(self, runner, mock_config_and_registry, tmp_path, monkeypatch):
        """Uninstall skill when not installed."""
        skills_dir = tmp_path / ".claude" / "skills"
        monkeypatch.setattr("crier.skill.GLOBAL_SKILLS_DIR", skills_dir)

        result = runner.invoke(cli, ["skill", "uninstall"])
        assert result.exit_code == 0
        assert "not installed" in result.output.lower()


class TestHelpers:
    """Tests for CLI helper functions."""

    def test_has_valid_front_matter(self, mock_config_and_registry):
        from crier.cli import _has_valid_front_matter

        # Valid front matter
        valid_file = mock_config_and_registry["posts_dir"] / "valid.md"
        valid_file.write_text("---\ntitle: Test\n---\nContent.")
        assert _has_valid_front_matter(valid_file) is True

        # No front matter
        no_fm_file = mock_config_and_registry["posts_dir"] / "no_fm.md"
        no_fm_file.write_text("Just content, no front matter.")
        # File without front matter still gets title from filename
        assert _has_valid_front_matter(no_fm_file) is True

        # Empty file
        empty_file = mock_config_and_registry["posts_dir"] / "empty.md"
        empty_file.write_text("")
        assert _has_valid_front_matter(empty_file) is True  # Title from filename

    def test_is_in_content_paths(self, mock_config_and_registry):
        from crier.cli import _is_in_content_paths

        posts_dir = mock_config_and_registry["posts_dir"]
        test_file = posts_dir / "test.md"
        test_file.write_text("---\ntitle: Test\n---\n")

        assert _is_in_content_paths(test_file) is True

        # File outside content paths
        outside_file = mock_config_and_registry["tmp_path"] / "outside.md"
        outside_file.write_text("---\ntitle: Test\n---\n")
        assert _is_in_content_paths(outside_file) is False

    def test_find_content_files(self, mock_config_and_registry):
        from crier.cli import _find_content_files

        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "test1.md").write_text("---\ntitle: Test 1\n---\nContent.")
        (posts_dir / "test2.md").write_text("---\ntitle: Test 2\n---\nContent.")
        (posts_dir / "no_title.md").write_text("Just content.")  # Still valid (title from filename)

        files = _find_content_files()
        assert len(files) >= 2
        filenames = [f.name for f in files]
        assert "test1.md" in filenames
        assert "test2.md" in filenames
