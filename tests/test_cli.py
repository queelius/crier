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

    def test_config_get_simple(self, runner, mock_config_and_registry):
        """Get a simple config value."""
        result = runner.invoke(cli, ["config", "get", "content_paths"])
        assert result.exit_code == 0
        assert "posts" in result.output

    def test_config_get_nested(self, runner, mock_config_and_registry):
        """Get a nested config value using dot notation."""
        result = runner.invoke(cli, ["config", "get", "platforms.devto.api_key"])
        assert result.exit_code == 0
        assert "test_devto_key" in result.output

    def test_config_get_json(self, runner, mock_config_and_registry):
        """Get config value as JSON."""
        result = runner.invoke(cli, ["config", "get", "platforms.devto", "--json"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["key"] == "platforms.devto"
        assert data["value"]["api_key"] == "test_devto_key"

    def test_config_get_missing_key(self, runner, mock_config_and_registry):
        """Get nonexistent key returns exit code 1."""
        result = runner.invoke(cli, ["config", "get", "nonexistent.key"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_config_get_missing_key_json(self, runner, mock_config_and_registry):
        """Get nonexistent key with --json returns null value."""
        result = runner.invoke(cli, ["config", "get", "nonexistent.key", "--json"])
        assert result.exit_code == 0  # JSON mode doesn't error
        import json
        data = json.loads(result.output)
        assert data["value"] is None


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


class TestLLMConfigCommands:
    """Tests for crier config llm subcommands."""

    def test_llm_show_not_configured(self, runner, mock_config_and_registry, monkeypatch):
        """Show LLM config when not configured."""
        # Clear any LLM-related env vars
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

        result = runner.invoke(cli, ["config", "llm", "show"])
        assert result.exit_code == 0
        assert "not configured" in result.output
        assert "LLM Configuration" in result.output

    def test_llm_show_with_env_var(self, runner, mock_config_and_registry, monkeypatch):
        """Show LLM config when OPENAI_API_KEY env var is set."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456789")
        result = runner.invoke(cli, ["config", "llm", "show"])
        assert result.exit_code == 0
        assert "configured" in result.output
        assert "sk-t" in result.output  # masked key shows first 4 chars
        assert "OPENAI_API_KEY" in result.output

    def test_llm_show_with_config(self, runner, mock_config_and_registry, tmp_path):
        """Show LLM config when configured in config file."""
        # Update config file to include LLM settings
        config_file = tmp_path / "config" / "config.yaml"
        config = yaml.safe_load(config_file.read_text())
        config["llm"] = {
            "api_key": "sk-configkey123",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
        }
        config_file.write_text(yaml.dump(config))

        result = runner.invoke(cli, ["config", "llm", "show"])
        assert result.exit_code == 0
        assert "configured" in result.output
        assert "gpt-4o-mini" in result.output
        assert "config" in result.output  # source is config

    def test_llm_set_api_key(self, runner, mock_config_and_registry, tmp_path):
        """Set LLM API key."""
        result = runner.invoke(cli, ["config", "llm", "set", "api_key", "sk-newkey123"])
        assert result.exit_code == 0
        assert "api_key set successfully" in result.output

        # Verify it was saved
        config_file = tmp_path / "config" / "config.yaml"
        config = yaml.safe_load(config_file.read_text())
        assert config.get("llm", {}).get("api_key") == "sk-newkey123"

    def test_llm_set_base_url(self, runner, mock_config_and_registry, tmp_path):
        """Set LLM base URL."""
        result = runner.invoke(cli, ["config", "llm", "set", "base_url", "http://localhost:11434/v1"])
        assert result.exit_code == 0
        assert "base_url set successfully" in result.output

        # Verify it was saved
        config_file = tmp_path / "config" / "config.yaml"
        config = yaml.safe_load(config_file.read_text())
        assert config.get("llm", {}).get("base_url") == "http://localhost:11434/v1"

    def test_llm_set_model(self, runner, mock_config_and_registry, tmp_path):
        """Set LLM model."""
        result = runner.invoke(cli, ["config", "llm", "set", "model", "llama3"])
        assert result.exit_code == 0
        assert "model set successfully" in result.output

        # Verify it was saved
        config_file = tmp_path / "config" / "config.yaml"
        config = yaml.safe_load(config_file.read_text())
        assert config.get("llm", {}).get("model") == "llama3"

    def test_llm_set_invalid_key(self, runner, mock_config_and_registry):
        """Set LLM with invalid key fails."""
        result = runner.invoke(cli, ["config", "llm", "set", "invalid_key", "value"])
        assert result.exit_code != 0

    def test_llm_test_not_configured(self, runner, mock_config_and_registry, monkeypatch):
        """Test LLM when not configured fails."""
        # Clear any LLM-related env vars
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

        result = runner.invoke(cli, ["config", "llm", "test"])
        assert result.exit_code != 0
        assert "not configured" in result.output

    def test_llm_test_success(self, runner, mock_config_and_registry, monkeypatch):
        """Test LLM connection succeeds with mocked provider."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")

        # Mock the provider's rewrite method
        from crier.llm import RewriteResult

        def mock_rewrite(self, title, body, max_chars, platform):
            return RewriteResult(text="Test response", model="gpt-4o-mini", tokens_used=10)

        monkeypatch.setattr("crier.llm.openai_compat.OpenAICompatProvider.rewrite", mock_rewrite)

        result = runner.invoke(cli, ["config", "llm", "test"])
        assert result.exit_code == 0
        assert "successful" in result.output
        assert "Test response" in result.output

    def test_llm_test_failure(self, runner, mock_config_and_registry, monkeypatch):
        """Test LLM connection fails with mocked error."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")

        # Mock the provider's rewrite method to raise an error
        from crier.llm import LLMProviderError

        def mock_rewrite(self, title, body, max_chars, platform):
            raise LLMProviderError("Connection refused")

        monkeypatch.setattr("crier.llm.openai_compat.OpenAICompatProvider.rewrite", mock_rewrite)

        result = runner.invoke(cli, ["config", "llm", "test"])
        assert result.exit_code != 0
        assert "failed" in result.output.lower()


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

    @patch("crier.cli.get_platform")
    def test_publish_json_output(self, mock_get_platform, runner, mock_config_and_registry):
        """Publish with --json outputs JSON format."""
        import json

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

        result = runner.invoke(cli, ["publish", str(test_file), "--to", "devto", "--json"])
        assert result.exit_code == 0

        # Parse JSON output
        output = json.loads(result.output)
        assert output["command"] == "publish"
        assert output["title"] == "Test Article"
        assert len(output["results"]) == 1
        assert output["results"][0]["success"] is True
        assert output["results"][0]["platform"] == "devto"
        assert output["summary"]["succeeded"] == 1

    def test_publish_batch_skips_manual_platforms(self, runner, mock_config_and_registry):
        """Publish with --batch skips manual mode platforms."""
        import json

        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("""\
---
title: Test Article
canonical_url: https://example.com/test
---

Content.
""")

        # Twitter is configured as manual mode in mock_config_and_registry
        result = runner.invoke(cli, ["publish", str(test_file), "--to", "twitter", "--batch"])
        assert result.exit_code == 0

        # Should output JSON (batch implies --json)
        output = json.loads(result.output)
        assert output["command"] == "publish"
        # Twitter should be skipped
        assert len(output["results"]) == 0
        assert len(output["skipped"]) == 1
        assert output["skipped"][0]["platform"] == "twitter"

    @patch("crier.cli.get_platform")
    def test_publish_batch_with_api_platform(self, mock_get_platform, runner, mock_config_and_registry):
        """Publish with --batch publishes to API platforms."""
        import json

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

        # DevTo is configured as API mode
        result = runner.invoke(cli, ["publish", str(test_file), "--to", "devto", "--batch"])
        assert result.exit_code == 0

        output = json.loads(result.output)
        assert output["summary"]["succeeded"] == 1
        assert len(output["skipped"]) == 0


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

    def test_audit_tag_filter(self, runner, mock_config_and_registry):
        """Audit with --tag filters content by tags."""
        posts_dir = mock_config_and_registry["posts_dir"]

        # Create posts with different tags
        (posts_dir / "python-post.md").write_text("""\
---
title: Python Post
tags: [python, testing]
canonical_url: https://example.com/python
---
Python content.
""")
        (posts_dir / "js-post.md").write_text("""\
---
title: JavaScript Post
tags: [javascript, web]
canonical_url: https://example.com/js
---
JS content.
""")

        result = runner.invoke(cli, ["audit", "--tag", "python"])
        assert result.exit_code == 0
        assert "python-post.md" in result.output
        assert "js-post.md" not in result.output

    def test_audit_tag_filter_multiple_or(self, runner, mock_config_and_registry):
        """Multiple --tag flags use OR logic."""
        posts_dir = mock_config_and_registry["posts_dir"]

        (posts_dir / "python-post.md").write_text("""\
---
title: Python Post
tags: [python]
canonical_url: https://example.com/python
---
Content.
""")
        (posts_dir / "js-post.md").write_text("""\
---
title: JS Post
tags: [javascript]
canonical_url: https://example.com/js
---
Content.
""")
        (posts_dir / "rust-post.md").write_text("""\
---
title: Rust Post
tags: [rust]
canonical_url: https://example.com/rust
---
Content.
""")

        result = runner.invoke(cli, ["audit", "--tag", "python", "--tag", "javascript"])
        assert result.exit_code == 0
        assert "python-post.md" in result.output
        assert "js-post.md" in result.output
        assert "rust-post.md" not in result.output

    def test_audit_tag_filter_case_insensitive(self, runner, mock_config_and_registry):
        """Tag filtering is case-insensitive."""
        posts_dir = mock_config_and_registry["posts_dir"]

        (posts_dir / "mixed-case.md").write_text("""\
---
title: Mixed Case
tags: [Python, MachineLearning]
canonical_url: https://example.com/mixed
---
Content.
""")

        result = runner.invoke(cli, ["audit", "--tag", "PYTHON"])
        assert result.exit_code == 0
        assert "mixed-case.md" in result.output

    def test_audit_tag_filter_excludes_untagged(self, runner, mock_config_and_registry):
        """Posts without tags are excluded when --tag is used."""
        posts_dir = mock_config_and_registry["posts_dir"]

        (posts_dir / "tagged.md").write_text("""\
---
title: Tagged
tags: [python]
canonical_url: https://example.com/tagged
---
Content.
""")
        (posts_dir / "untagged.md").write_text("""\
---
title: Untagged
canonical_url: https://example.com/untagged
---
Content.
""")

        result = runner.invoke(cli, ["audit", "--tag", "python"])
        assert result.exit_code == 0
        assert "tagged.md" in result.output
        assert "untagged.md" not in result.output

    def test_audit_tag_filter_string_format(self, runner, mock_config_and_registry):
        """Tag filtering works with comma-separated string format."""
        posts_dir = mock_config_and_registry["posts_dir"]

        (posts_dir / "string-tags.md").write_text("""\
---
title: String Tags
tags: "python, testing, crier"
canonical_url: https://example.com/string
---
Content.
""")

        result = runner.invoke(cli, ["audit", "--tag", "testing"])
        assert result.exit_code == 0
        assert "string-tags.md" in result.output


class TestGetContentTags:
    """Tests for _get_content_tags helper function."""

    def test_get_content_tags_list_format(self, tmp_path):
        """Test _get_content_tags with list format."""
        md_file = tmp_path / "tagged.md"
        md_file.write_text("""\
---
title: Tagged Post
tags: [Python, Testing, CRIER]
---

Content.
""")
        from crier.cli import _get_content_tags
        tags = _get_content_tags(md_file)
        assert tags == ["python", "testing", "crier"]  # Normalized to lowercase

    def test_get_content_tags_string_format(self, tmp_path):
        """Test _get_content_tags with comma-separated string."""
        md_file = tmp_path / "tagged.md"
        md_file.write_text("""\
---
title: Tagged Post
tags: "Python, Testing, CRIER"
---

Content.
""")
        from crier.cli import _get_content_tags
        tags = _get_content_tags(md_file)
        assert tags == ["python", "testing", "crier"]

    def test_get_content_tags_no_tags(self, tmp_path):
        """Test _get_content_tags with no tags field."""
        md_file = tmp_path / "untagged.md"
        md_file.write_text("""\
---
title: No Tags
---

Content.
""")
        from crier.cli import _get_content_tags
        tags = _get_content_tags(md_file)
        assert tags == []

    def test_get_content_tags_no_front_matter(self, tmp_path):
        """Test _get_content_tags with no front matter."""
        md_file = tmp_path / "plain.md"
        md_file.write_text("Just content, no front matter.")

        from crier.cli import _get_content_tags
        tags = _get_content_tags(md_file)
        assert tags == []


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


class TestTruncateAtSentence:
    """Tests for _truncate_at_sentence helper function."""

    def test_no_truncation_needed(self):
        """Test text that fits within limit."""
        from crier.cli import _truncate_at_sentence
        text = "Short text."
        result = _truncate_at_sentence(text, 100)
        assert result == text

    def test_truncate_at_period(self):
        """Test truncation at sentence boundary (period)."""
        from crier.cli import _truncate_at_sentence
        text = "First sentence. Second sentence. Third sentence."
        result = _truncate_at_sentence(text, 35)
        assert result == "First sentence. Second sentence."
        assert len(result) <= 35

    def test_truncate_at_question_mark(self):
        """Test truncation at question mark."""
        from crier.cli import _truncate_at_sentence
        text = "Is this a question? Yes it is. More text."
        result = _truncate_at_sentence(text, 25)
        assert result == "Is this a question?"
        assert len(result) <= 25

    def test_truncate_at_exclamation(self):
        """Test truncation at exclamation mark."""
        from crier.cli import _truncate_at_sentence
        text = "Wow this is great! More content here."
        result = _truncate_at_sentence(text, 25)
        assert result == "Wow this is great!"
        assert len(result) <= 25

    def test_fallback_to_word_boundary(self):
        """Test fallback to word boundary when no sentence end in reasonable range."""
        from crier.cli import _truncate_at_sentence
        text = "This is a very long single sentence without any breaks that goes on and on"
        result = _truncate_at_sentence(text, 50)
        assert len(result) <= 50
        assert result.endswith("...")

    def test_hard_truncate_fallback(self):
        """Test hard truncation when no good boundary."""
        from crier.cli import _truncate_at_sentence
        text = "Superlongwordwithnospacesthatjustkeepsgoingandgoing"
        result = _truncate_at_sentence(text, 30)
        assert len(result) <= 30
        assert result.endswith("...")


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


class TestSearchCommand:
    """Tests for crier search command."""

    def test_search_lists_files(self, runner, mock_config_and_registry):
        """Basic file listing works."""
        import json

        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "post1.md").write_text(
            "---\ntitle: First Post\ndate: 2025-01-01\ntags: [python]\n---\nHello world."
        )
        (posts_dir / "post2.md").write_text(
            "---\ntitle: Second Post\ndate: 2025-01-02\n---\nGoodbye world."
        )

        result = runner.invoke(cli, ["search", str(posts_dir), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["count"] == 2
        titles = [r["title"] for r in data["results"]]
        assert "First Post" in titles
        assert "Second Post" in titles

    def test_search_tag_filter(self, runner, mock_config_and_registry):
        """Tag filtering works."""
        import json

        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "python-post.md").write_text(
            "---\ntitle: Python Post\ntags: [python, testing]\n---\nContent."
        )
        (posts_dir / "javascript-post.md").write_text(
            "---\ntitle: JS Post\ntags: [javascript]\n---\nContent."
        )

        result = runner.invoke(cli, ["search", str(posts_dir), "--tag", "python", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["count"] == 1
        assert data["results"][0]["title"] == "Python Post"

    def test_search_date_filter(self, runner, mock_config_and_registry):
        """Date filtering works."""
        import json

        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "old.md").write_text(
            "---\ntitle: Old Post\ndate: 2024-01-01\n---\nOld content."
        )
        (posts_dir / "new.md").write_text(
            "---\ntitle: New Post\ndate: 2025-12-01\n---\nNew content."
        )

        result = runner.invoke(cli, ["search", str(posts_dir), "--since", "2025-01-01", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["count"] == 1
        assert data["results"][0]["title"] == "New Post"

    def test_search_json_output(self, runner, mock_config_and_registry):
        """JSON output format works."""
        import json

        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "test.md").write_text(
            "---\ntitle: Test Article\ndate: 2025-01-15\ntags: [testing, python]\n---\nThis is some content."
        )

        result = runner.invoke(cli, ["search", str(posts_dir), "--json"])
        assert result.exit_code == 0

        data = json.loads(result.output)
        assert "results" in data
        assert "count" in data
        assert data["count"] == 1
        assert data["results"][0]["title"] == "Test Article"
        assert "testing" in data["results"][0]["tags"]
        assert "python" in data["results"][0]["tags"]
        assert data["results"][0]["words"] > 0

    def test_search_sample(self, runner, mock_config_and_registry):
        """Sampling works."""
        import json

        posts_dir = mock_config_and_registry["posts_dir"]
        for i in range(10):
            (posts_dir / f"post{i}.md").write_text(f"---\ntitle: Post {i}\n---\nContent.")

        result = runner.invoke(cli, ["search", str(posts_dir), "--sample", "3", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["count"] == 3

    def test_search_no_files(self, runner, mock_config_and_registry):
        """Empty result handling."""
        posts_dir = mock_config_and_registry["posts_dir"]
        # No files created
        result = runner.invoke(cli, ["search", str(posts_dir)])
        assert result.exit_code == 0
        assert "No content files found" in result.output

    def test_search_no_files_json(self, runner, mock_config_and_registry):
        """Empty result JSON output."""
        import json

        posts_dir = mock_config_and_registry["posts_dir"]
        result = runner.invoke(cli, ["search", str(posts_dir), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["results"] == []
        assert data["count"] == 0

    def test_search_combined_filters(self, runner, mock_config_and_registry):
        """Multiple filters can be combined."""
        import json

        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "match.md").write_text(
            "---\ntitle: Matching Post\ndate: 2025-06-01\ntags: [python]\n---\nContent."
        )
        (posts_dir / "wrong-tag.md").write_text(
            "---\ntitle: Wrong Tag\ndate: 2025-06-01\ntags: [javascript]\n---\nContent."
        )
        (posts_dir / "old-date.md").write_text(
            "---\ntitle: Old Date\ndate: 2024-01-01\ntags: [python]\n---\nContent."
        )

        result = runner.invoke(cli, ["search", str(posts_dir), "--tag", "python", "--since", "2025-01-01", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["count"] == 1
        assert data["results"][0]["title"] == "Matching Post"

    def test_search_quiet_suppresses_output(self, runner, mock_config_and_registry):
        """--quiet flag suppresses non-essential output."""
        posts_dir = mock_config_and_registry["posts_dir"]
        # No files - should suppress "No content files found" message
        result = runner.invoke(cli, ["search", str(posts_dir), "--quiet"])
        assert result.exit_code == 0
        assert "No content files found" not in result.output


class TestLLMConfigSetNewFields:
    """Tests for new LLM config fields (temperature, retry_count, truncate_fallback)."""

    def test_llm_set_temperature(self, runner, mock_config_and_registry, tmp_path):
        """Set LLM temperature."""
        result = runner.invoke(cli, ["config", "llm", "set", "temperature", "1.2"])
        assert result.exit_code == 0
        assert "temperature set successfully" in result.output

        # Verify it was saved
        config_file = tmp_path / "config" / "config.yaml"
        config = yaml.safe_load(config_file.read_text())
        assert config.get("llm", {}).get("temperature") == 1.2

    def test_llm_set_retry_count(self, runner, mock_config_and_registry, tmp_path):
        """Set LLM retry count."""
        result = runner.invoke(cli, ["config", "llm", "set", "retry_count", "3"])
        assert result.exit_code == 0
        assert "retry_count set successfully" in result.output

        # Verify it was saved
        config_file = tmp_path / "config" / "config.yaml"
        config = yaml.safe_load(config_file.read_text())
        assert config.get("llm", {}).get("retry_count") == 3

    def test_llm_set_truncate_fallback(self, runner, mock_config_and_registry, tmp_path):
        """Set LLM truncate fallback."""
        result = runner.invoke(cli, ["config", "llm", "set", "truncate_fallback", "true"])
        assert result.exit_code == 0
        assert "truncate_fallback set successfully" in result.output

        # Verify it was saved
        config_file = tmp_path / "config" / "config.yaml"
        config = yaml.safe_load(config_file.read_text())
        assert config.get("llm", {}).get("truncate_fallback") is True

    def test_llm_show_displays_new_fields(self, runner, mock_config_and_registry, tmp_path):
        """Show LLM config displays new fields."""
        # Update config file to include new LLM settings
        config_file = tmp_path / "config" / "config.yaml"
        config = yaml.safe_load(config_file.read_text())
        config["llm"] = {
            "api_key": "sk-test",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
            "temperature": 0.9,
            "retry_count": 2,
            "truncate_fallback": True,
        }
        config_file.write_text(yaml.dump(config))

        result = runner.invoke(cli, ["config", "llm", "show"])
        assert result.exit_code == 0
        assert "temperature" in result.output.lower()
        assert "0.9" in result.output
        assert "retry" in result.output.lower()
        assert "truncate" in result.output.lower()


class TestRewriteValidation:
    """Tests for --rewrite content length validation."""

    def test_rewrite_too_long_fails(self, runner, mock_config_and_registry):
        """Manual --rewrite that exceeds platform limit should fail."""
        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com\n---\nContent.")

        # Bluesky limit is 300 chars
        long_rewrite = "x" * 400
        result = runner.invoke(cli, ["publish", str(test_file), "--to", "bluesky", "--rewrite", long_rewrite])
        # Should fail (exit code != 0 or partial success exit code 2)
        assert "too long" in result.output.lower() or result.exit_code != 0

    def test_rewrite_too_long_json_output(self, runner, mock_config_and_registry):
        """Manual --rewrite too long with --json outputs proper error."""
        import json

        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com\n---\nContent.")

        long_rewrite = "x" * 400
        result = runner.invoke(cli, ["publish", str(test_file), "--to", "bluesky", "--rewrite", long_rewrite, "--json"])

        output = json.loads(result.output)
        assert output["results"][0]["success"] is False
        assert "too long" in output["results"][0]["error"].lower()

    def test_rewrite_within_limit_succeeds(self, runner, mock_config_and_registry):
        """Manual --rewrite within limit should proceed to publish."""
        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com\n---\nContent.")

        # 200 chars is within bluesky's 300 char limit
        short_rewrite = "x" * 200
        # Dry-run to check validation passes (actual publish would need mocking)
        result = runner.invoke(cli, ["publish", str(test_file), "--to", "bluesky", "--rewrite", short_rewrite, "--dry-run"])
        assert "too long" not in result.output.lower()
        assert result.exit_code == 0


class TestAutoRewriteCLIOptions:
    """Tests for new auto-rewrite CLI options."""

    def test_auto_rewrite_retry_option_exists(self, runner, mock_config_and_registry):
        """Verify --auto-rewrite-retry option exists."""
        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        # Should not error on --auto-rewrite-retry (but may fail for other reasons like no LLM)
        result = runner.invoke(cli, ["publish", str(test_file), "--to", "bluesky", "--dry-run", "--auto-rewrite-retry", "3"])
        # Verify the option was recognized (no "no such option" error)
        assert "no such option" not in result.output.lower()

    def test_auto_rewrite_truncate_option_exists(self, runner, mock_config_and_registry):
        """Verify --auto-rewrite-truncate option exists."""
        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        result = runner.invoke(cli, ["publish", str(test_file), "--to", "bluesky", "--dry-run", "--auto-rewrite-truncate"])
        assert "no such option" not in result.output.lower()

    def test_temperature_option_exists(self, runner, mock_config_and_registry):
        """Verify --temperature option exists."""
        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        result = runner.invoke(cli, ["publish", str(test_file), "--to", "bluesky", "--dry-run", "--temperature", "1.2"])
        assert "no such option" not in result.output.lower()

    def test_model_override_option_exists(self, runner, mock_config_and_registry):
        """Verify --model option exists."""
        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        result = runner.invoke(cli, ["publish", str(test_file), "--to", "bluesky", "--dry-run", "--model", "gpt-4o"])
        assert "no such option" not in result.output.lower()

    def test_short_retry_option(self, runner, mock_config_and_registry):
        """Verify -R short option for retry works."""
        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        result = runner.invoke(cli, ["publish", str(test_file), "--to", "bluesky", "--dry-run", "-R", "2"])
        assert "no such option" not in result.output.lower()


class TestAutomationFlags:
    """Tests for automation flags (--yes, --quiet, exit codes)."""

    def test_publish_json_error_format(self, runner, mock_config_and_registry):
        """Errors output as JSON when --json is used."""
        import json

        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "test.md").write_text("---\ntitle: Test\n---\nContent.")

        # Unknown profile should output JSON error
        result = runner.invoke(cli, ["publish", str(posts_dir / "test.md"), "--profile", "nonexistent", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["success"] is False
        assert "nonexistent" in data["error"].lower()

    def test_publish_no_platform_json_error(self, runner, mock_config_and_registry):
        """No platform error outputs as JSON."""
        import json

        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "test.md").write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        # Mock to remove default_profile
        result = runner.invoke(cli, ["publish", str(posts_dir / "test.md"), "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["success"] is False
        assert "platform" in data["error"].lower()

    def test_audit_json_error_format(self, runner, mock_config_and_registry):
        """Audit errors output as JSON when --json is used."""
        import json

        # Unknown profile should output JSON error
        result = runner.invoke(cli, ["audit", "--profile", "nonexistent", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["success"] is False
        assert "nonexistent" in data["error"].lower()
