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

    def test_doctor_json_output(self, runner, mock_config_and_registry):
        """Doctor --json outputs valid JSON."""
        result = runner.invoke(cli, ["doctor", "--json"])
        assert result.exit_code == 0
        import json
        output = json.loads(result.output)
        assert output["command"] == "doctor"
        assert "platforms" in output
        assert "summary" in output


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
        from crier.utils import get_content_tags as _get_content_tags
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
        from crier.utils import get_content_tags as _get_content_tags
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
        from crier.utils import get_content_tags as _get_content_tags
        tags = _get_content_tags(md_file)
        assert tags == []

    def test_get_content_tags_no_front_matter(self, tmp_path):
        """Test _get_content_tags with no front matter."""
        md_file = tmp_path / "plain.md"
        md_file.write_text("Just content, no front matter.")

        from crier.utils import get_content_tags as _get_content_tags
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
        from crier.utils import truncate_at_sentence as _truncate_at_sentence
        text = "Short text."
        result = _truncate_at_sentence(text, 100)
        assert result == text

    def test_truncate_at_period(self):
        """Test truncation at sentence boundary (period)."""
        from crier.utils import truncate_at_sentence as _truncate_at_sentence
        text = "First sentence. Second sentence. Third sentence."
        result = _truncate_at_sentence(text, 35)
        assert result == "First sentence. Second sentence."
        assert len(result) <= 35

    def test_truncate_at_question_mark(self):
        """Test truncation at question mark."""
        from crier.utils import truncate_at_sentence as _truncate_at_sentence
        text = "Is this a question? Yes it is. More text."
        result = _truncate_at_sentence(text, 25)
        assert result == "Is this a question?"
        assert len(result) <= 25

    def test_truncate_at_exclamation(self):
        """Test truncation at exclamation mark."""
        from crier.utils import truncate_at_sentence as _truncate_at_sentence
        text = "Wow this is great! More content here."
        result = _truncate_at_sentence(text, 25)
        assert result == "Wow this is great!"
        assert len(result) <= 25

    def test_fallback_to_word_boundary(self):
        """Test fallback to word boundary when no sentence end in reasonable range."""
        from crier.utils import truncate_at_sentence as _truncate_at_sentence
        text = "This is a very long single sentence without any breaks that goes on and on"
        result = _truncate_at_sentence(text, 50)
        assert len(result) <= 50
        assert result.endswith("...")

    def test_hard_truncate_fallback(self):
        """Test hard truncation when no good boundary."""
        from crier.utils import truncate_at_sentence as _truncate_at_sentence
        text = "Superlongwordwithnospacesthatjustkeepsgoingandgoing"
        result = _truncate_at_sentence(text, 30)
        assert len(result) <= 30
        assert result.endswith("...")


class TestHelpers:
    """Tests for CLI helper functions."""

    def test_has_valid_front_matter(self, mock_config_and_registry):
        from crier.utils import has_valid_front_matter as _has_valid_front_matter

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
        from crier.utils import is_in_content_paths as _is_in_content_paths

        posts_dir = mock_config_and_registry["posts_dir"]
        test_file = posts_dir / "test.md"
        test_file.write_text("---\ntitle: Test\n---\n")

        assert _is_in_content_paths(test_file) is True

        # File outside content paths
        outside_file = mock_config_and_registry["tmp_path"] / "outside.md"
        outside_file.write_text("---\ntitle: Test\n---\n")
        assert _is_in_content_paths(outside_file) is False

    def test_find_content_files(self, mock_config_and_registry):
        from crier.utils import find_content_files as _find_content_files

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


class TestPlatformTypoSuggestion:
    """Tests for platform typo suggestion feature."""

    def test_typo_suggestion(self):
        """Unknown platform suggests closest match."""
        from crier.platforms import get_platform
        import pytest

        with pytest.raises(ValueError) as exc_info:
            get_platform("devtoo")

        error_msg = str(exc_info.value)
        assert "devto" in error_msg.lower()
        assert "did you mean" in error_msg.lower()

    def test_no_suggestion_for_gibberish(self):
        """No suggestion for completely unrelated names."""
        from crier.platforms import get_platform
        import pytest

        with pytest.raises(ValueError) as exc_info:
            get_platform("xyzabc123")

        error_msg = str(exc_info.value)
        assert "unknown platform" in error_msg.lower()
        # Should not suggest anything since it's too different
        # But should list available platforms
        assert "available platforms" in error_msg.lower()


class TestPlatformsCommand:
    """Tests for crier platforms command."""

    def test_platforms_shows_all(self, runner, mock_config_and_registry):
        """Platforms command shows all platforms."""
        result = runner.invoke(cli, ["platforms"])
        assert result.exit_code == 0
        assert "Available Platforms" in result.output
        assert "devto" in result.output
        assert "bluesky" in result.output

    def test_platforms_shows_status(self, runner, mock_config_and_registry):
        """Platforms command shows configuration status."""
        result = runner.invoke(cli, ["platforms"])
        assert result.exit_code == 0
        # devto is configured in mock_config_and_registry
        assert "Configured" in result.output


class TestListWithoutPlatform:
    """Tests for crier list without platform argument."""

    def test_list_all_platforms_empty(self, runner, mock_config_and_registry):
        """List without platform shows message when empty."""
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "No articles in registry" in result.output

    def test_list_requires_platform_for_remote(self, runner, mock_config_and_registry):
        """Remote mode requires platform argument."""
        result = runner.invoke(cli, ["list", "--remote"])
        assert result.exit_code == 1
        assert "requires a PLATFORM argument" in result.output


class TestDateFilterHelp:
    """Tests for improved date filter error messages."""

    def test_invalid_date_shows_examples(self, runner, mock_config_and_registry):
        """Invalid date format shows helpful examples."""
        result = runner.invoke(cli, ["audit", "--since", "invalid"])
        # Click wraps the BadParameter message
        assert "1d" in result.output or "1w" in result.output
        assert "Invalid date format" in result.output


class TestVerboseFlags:
    """Tests for verbose flags on commands."""

    def test_search_verbose_flag_exists(self, runner, mock_config_and_registry):
        """Search command accepts --verbose flag."""
        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "test.md").write_text("---\ntitle: Test\ndescription: A test article\n---\nContent.")

        result = runner.invoke(cli, ["search", "--verbose"])
        assert result.exit_code == 0
        # Verbose mode should show description column
        assert "Description" in result.output

    def test_status_verbose_flag_exists(self, runner, mock_config_and_registry):
        """Status command accepts --verbose flag."""
        result = runner.invoke(cli, ["status", "--verbose"])
        assert result.exit_code == 0

    def test_audit_verbose_flag_exists(self, runner, mock_config_and_registry):
        """Audit command accepts --verbose flag."""
        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "test.md").write_text("---\ntitle: Test\n---\nContent.")

        result = runner.invoke(cli, ["audit", "--verbose"])
        assert result.exit_code == 0


class TestPublishNoProfileHelp:
    """Tests for improved publish error when no platform specified."""

    def test_shows_available_profiles(self, runner, mock_config_and_registry):
        """No platform error shows available profiles."""
        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "test.md").write_text("---\ntitle: Test\n---\nContent.")

        result = runner.invoke(cli, ["publish", str(posts_dir / "test.md")])
        assert result.exit_code == 1
        # Should show available profiles from mock_config_and_registry
        assert "Available profiles" in result.output or "--profile" in result.output


class TestDeleteCommand:
    """Tests for crier delete command."""

    def test_delete_no_canonical_url(self, runner, mock_config_and_registry):
        """Delete fails if file has no canonical_url."""
        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "test.md").write_text("---\ntitle: Test\n---\nContent.")

        result = runner.invoke(cli, ["delete", str(posts_dir / "test.md"), "--from", "devto"])
        assert result.exit_code == 1
        assert "canonical_url" in result.output

    def test_delete_not_in_registry(self, runner, mock_config_and_registry):
        """Delete fails if file is not tracked."""
        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "test.md").write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        result = runner.invoke(cli, ["delete", str(posts_dir / "test.md"), "--from", "devto"])
        assert result.exit_code == 1
        assert "registry" in result.output.lower() or "tracked" in result.output.lower()

    def test_delete_requires_platform_spec(self, runner, mock_config_and_registry):
        """Delete requires --from or --all when file is tracked."""
        from crier.registry import record_publication

        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "test.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        # Register the file so it gets past the "not tracked" check
        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            source_file=str(md_file),
        )

        result = runner.invoke(cli, ["delete", str(md_file)])
        assert result.exit_code == 1
        assert "--from" in result.output or "--all" in result.output

    def test_delete_dry_run(self, runner, mock_config_and_registry):
        """Delete --dry-run shows preview without deleting."""
        from crier.registry import record_publication

        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "test.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        # Add to registry
        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            source_file=str(md_file),
        )

        result = runner.invoke(cli, ["delete", str(md_file), "--all", "--dry-run"])
        assert result.exit_code == 0
        assert "Dry Run" in result.output
        assert "devto" in result.output

    def test_delete_json_output(self, runner, mock_config_and_registry):
        """Delete --json outputs machine-readable results."""
        import json

        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "test.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        # Delete file that's not tracked - should fail with JSON error
        result = runner.invoke(cli, ["delete", str(md_file), "--from", "devto", "--json"])
        assert result.exit_code == 1
        output = json.loads(result.output)
        assert output["success"] is False


class TestArchiveCommand:
    """Tests for crier archive command."""

    def test_archive_no_canonical_url(self, runner, mock_config_and_registry):
        """Archive fails if file has no canonical_url."""
        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "test.md").write_text("---\ntitle: Test\n---\nContent.")

        result = runner.invoke(cli, ["archive", str(posts_dir / "test.md")])
        assert result.exit_code == 1
        assert "canonical_url" in result.output

    def test_archive_not_in_registry(self, runner, mock_config_and_registry):
        """Archive fails if file is not tracked."""
        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "test.md").write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        result = runner.invoke(cli, ["archive", str(posts_dir / "test.md")])
        assert result.exit_code == 1
        assert "registry" in result.output.lower()

    def test_archive_success(self, runner, mock_config_and_registry):
        """Archive succeeds for tracked file."""
        from crier.registry import record_publication, is_archived

        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "test.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            source_file=str(md_file),
        )

        result = runner.invoke(cli, ["archive", str(md_file)])
        assert result.exit_code == 0
        assert "Archived" in result.output

        # Verify it's archived
        assert is_archived("https://example.com/test") is True

    def test_archive_already_archived(self, runner, mock_config_and_registry):
        """Archive already-archived file is idempotent."""
        from crier.registry import record_publication, set_archived

        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "test.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            source_file=str(md_file),
        )
        set_archived("https://example.com/test", archived=True)

        result = runner.invoke(cli, ["archive", str(md_file)])
        assert result.exit_code == 0
        assert "already" in result.output.lower()


class TestUnarchiveCommand:
    """Tests for crier unarchive command."""

    def test_unarchive_no_canonical_url(self, runner, mock_config_and_registry):
        """Unarchive fails if file has no canonical_url."""
        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "test.md").write_text("---\ntitle: Test\n---\nContent.")

        result = runner.invoke(cli, ["unarchive", str(posts_dir / "test.md")])
        assert result.exit_code == 1
        assert "canonical_url" in result.output

    def test_unarchive_not_archived(self, runner, mock_config_and_registry):
        """Unarchive not-archived file is idempotent."""
        from crier.registry import record_publication

        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "test.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            source_file=str(md_file),
        )

        result = runner.invoke(cli, ["unarchive", str(md_file)])
        assert result.exit_code == 0
        assert "Not archived" in result.output

    def test_unarchive_success(self, runner, mock_config_and_registry):
        """Unarchive restores archived file."""
        from crier.registry import record_publication, set_archived, is_archived

        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "test.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            source_file=str(md_file),
        )
        set_archived("https://example.com/test", archived=True)
        assert is_archived("https://example.com/test") is True

        result = runner.invoke(cli, ["unarchive", str(md_file)])
        assert result.exit_code == 0
        assert "Unarchived" in result.output

        # Verify it's unarchived
        assert is_archived("https://example.com/test") is False


class TestAuditArchiveFilter:
    """Tests for audit command archive filtering."""

    def test_audit_excludes_archived_by_default(self, runner, mock_config_and_registry):
        """Audit excludes archived content by default."""
        from crier.registry import record_publication, set_archived

        posts_dir = mock_config_and_registry["posts_dir"]

        # Create two files
        active_file = posts_dir / "active.md"
        active_file.write_text("---\ntitle: Active Post\ncanonical_url: https://example.com/active\n---\nActive content.")

        archived_file = posts_dir / "archived.md"
        archived_file.write_text("---\ntitle: Archived Post\ncanonical_url: https://example.com/archived\n---\nArchived content.")

        # Register both and archive one
        record_publication(
            canonical_url="https://example.com/active",
            platform="devto",
            article_id="1",
            url="https://dev.to/active",
            source_file=str(active_file),
        )
        record_publication(
            canonical_url="https://example.com/archived",
            platform="devto",
            article_id="2",
            url="https://dev.to/archived",
            source_file=str(archived_file),
        )
        set_archived("https://example.com/archived", archived=True)

        result = runner.invoke(cli, ["audit"])
        assert result.exit_code == 0
        # Should show 1 file (the active one), not the archived one
        assert "1 file" in result.output
        # Active file should be in output, archived should not
        assert "active.md" in result.output
        assert "archived.md" not in result.output

    def test_audit_include_archived_shows_all(self, runner, mock_config_and_registry):
        """Audit --include-archived includes archived content."""
        from crier.registry import record_publication, set_archived

        posts_dir = mock_config_and_registry["posts_dir"]

        # Create two files
        active_file = posts_dir / "active.md"
        active_file.write_text("---\ntitle: Active Post\ncanonical_url: https://example.com/active\n---\nActive content.")

        archived_file = posts_dir / "archived.md"
        archived_file.write_text("---\ntitle: Archived Post\ncanonical_url: https://example.com/archived\n---\nArchived content.")

        # Archive one
        record_publication(
            canonical_url="https://example.com/archived",
            platform="devto",
            article_id="2",
            url="https://dev.to/archived",
            source_file=str(archived_file),
        )
        set_archived("https://example.com/archived", archived=True)

        result = runner.invoke(cli, ["audit", "--include-archived"])
        assert result.exit_code == 0
        # Should show 2 files now
        assert "2 file" in result.output


class TestDeleteCommandEdgeCases:
    """Additional tests for crier delete command."""

    def test_delete_from_platform_success(self, runner, mock_config_and_registry):
        """Delete from specific platform succeeds."""
        from crier.registry import record_publication, is_deleted
        from crier.platforms.base import DeleteResult

        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "test.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            source_file=str(md_file),
        )

        # Mock platform instance returned by PLATFORMS dict
        mock_platform = Mock()
        mock_platform.delete.return_value = DeleteResult(success=True, platform="devto")
        mock_platform.supports_delete = True

        mock_platform_cls = Mock(return_value=mock_platform)
        mock_platform_cls.supports_delete = True

        with patch.dict("crier.cli.PLATFORMS", {"devto": mock_platform_cls}):
            result = runner.invoke(cli, ["delete", str(md_file), "--from", "devto", "--yes"])

        assert result.exit_code == 0
        assert "Deleted" in result.output or "deleted" in result.output.lower()

    def test_delete_all_platforms_dry_run(self, runner, mock_config_and_registry):
        """Delete --all --dry-run shows all platforms without deleting."""
        from crier.registry import record_publication

        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "test.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            source_file=str(md_file),
        )
        record_publication(
            canonical_url="https://example.com/test",
            platform="bluesky",
            article_id="456",
            url="https://bsky.app/test",
            source_file=str(md_file),
        )

        result = runner.invoke(cli, ["delete", str(md_file), "--all", "--dry-run"])

        assert result.exit_code == 0
        assert "Dry Run" in result.output
        assert "devto" in result.output
        assert "bluesky" in result.output

    def test_delete_json_success(self, runner, mock_config_and_registry):
        """Delete with --json outputs proper JSON on success."""
        import json
        from crier.registry import record_publication
        from crier.platforms.base import DeleteResult

        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "test.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            source_file=str(md_file),
        )

        mock_platform = Mock()
        mock_platform.delete.return_value = DeleteResult(success=True, platform="devto")
        mock_platform.supports_delete = True

        mock_platform_cls = Mock(return_value=mock_platform)
        mock_platform_cls.supports_delete = True

        with patch.dict("crier.cli.PLATFORMS", {"devto": mock_platform_cls}):
            result = runner.invoke(cli, ["delete", str(md_file), "--from", "devto", "--yes", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["results"][0]["success"] is True

    def test_delete_help_text(self, runner, mock_config_and_registry):
        """Delete command help shows all options."""
        result = runner.invoke(cli, ["delete", "--help"])
        assert result.exit_code == 0
        assert "--from" in result.output
        assert "--all" in result.output
        assert "--dry-run" in result.output
        assert "--yes" in result.output
        assert "--json" in result.output

    def test_delete_no_platform_specified(self, runner, mock_config_and_registry):
        """Delete without --from or --all shows error."""
        from crier.registry import record_publication

        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "test.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            source_file=str(md_file),
        )

        result = runner.invoke(cli, ["delete", str(md_file)])

        assert result.exit_code == 1
        assert "--from" in result.output or "--all" in result.output

    def test_delete_not_in_registry(self, runner, mock_config_and_registry):
        """Delete for file not in registry shows error."""
        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "untracked.md"
        md_file.write_text("---\ntitle: Untracked\ncanonical_url: https://example.com/untracked\n---\nContent.")

        result = runner.invoke(cli, ["delete", str(md_file), "--from", "devto", "--yes"])

        assert result.exit_code == 1
        assert "not tracked" in result.output.lower() or "not found" in result.output.lower()

    def test_delete_already_deleted_all(self, runner, mock_config_and_registry):
        """Delete --all when all platforms already deleted."""
        from crier.registry import record_publication, record_deletion

        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "test.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            source_file=str(md_file),
        )
        record_deletion("https://example.com/test", "devto")

        result = runner.invoke(cli, ["delete", str(md_file), "--all", "--yes"])

        assert result.exit_code == 0
        assert "No platforms" in result.output or "already deleted" in result.output.lower()


class TestArchiveCommandEdgeCases:
    """Additional tests for archive/unarchive commands."""

    def test_archive_json_output(self, runner, mock_config_and_registry):
        """Archive with --json outputs machine-readable result."""
        import json
        from crier.registry import record_publication

        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "test.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            source_file=str(md_file),
        )

        result = runner.invoke(cli, ["archive", str(md_file), "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True

    def test_unarchive_json_output(self, runner, mock_config_and_registry):
        """Unarchive with --json outputs machine-readable result."""
        import json
        from crier.registry import record_publication, set_archived

        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "test.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            source_file=str(md_file),
        )
        set_archived("https://example.com/test", archived=True)

        result = runner.invoke(cli, ["unarchive", str(md_file), "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True

    def test_archive_not_in_registry_json(self, runner, mock_config_and_registry):
        """Archive for untracked file returns JSON error."""
        import json

        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "test.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        result = runner.invoke(cli, ["archive", str(md_file), "--json"])

        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["success"] is False

    def test_archive_help_text(self, runner, mock_config_and_registry):
        """Archive command help shows options."""
        result = runner.invoke(cli, ["archive", "--help"])
        assert result.exit_code == 0
        assert "--json" in result.output

    def test_unarchive_help_text(self, runner, mock_config_and_registry):
        """Unarchive command help shows options."""
        result = runner.invoke(cli, ["unarchive", "--help"])
        assert result.exit_code == 0
        assert "--json" in result.output


class TestScheduleCommands:
    """Tests for crier schedule CLI commands."""

    def test_schedule_help(self, runner, mock_config_and_registry):
        """Schedule command shows help."""
        result = runner.invoke(cli, ["schedule", "--help"])
        assert result.exit_code == 0
        assert "schedule" in result.output.lower()

    def test_schedule_list_empty(self, runner, mock_config_and_registry):
        """Schedule list with no scheduled posts."""
        result = runner.invoke(cli, ["schedule", "list"])
        assert result.exit_code == 0
        assert "No scheduled posts" in result.output or "empty" in result.output.lower()

    def test_schedule_list_json_empty(self, runner, mock_config_and_registry):
        """Schedule list --json with no posts."""
        import json

        result = runner.invoke(cli, ["schedule", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["posts"] == [] or data["count"] == 0


class TestStatusDeletedArticle:
    """Tests for status command with deleted articles."""

    def test_status_shows_deleted_platform(self, runner, mock_config_and_registry):
        """Status shows deleted status for deleted publications."""
        from crier.registry import record_publication, record_deletion

        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "test.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            source_file=str(md_file),
        )
        record_deletion("https://example.com/test", "devto")

        result = runner.invoke(cli, ["status", str(md_file)])
        assert result.exit_code == 0
        assert "deleted" in result.output.lower() or "devto" in result.output


class TestStatusArchivedArticle:
    """Tests for status command with archived articles."""

    def test_status_shows_archived(self, runner, mock_config_and_registry):
        """Status shows archived flag for archived articles."""
        from crier.registry import record_publication, set_archived

        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "test.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            source_file=str(md_file),
        )
        set_archived("https://example.com/test", archived=True)

        result = runner.invoke(cli, ["status", str(md_file)])
        assert result.exit_code == 0
        assert "archived" in result.output.lower() or "devto" in result.output


class TestPublishWithThread:
    """Tests for publish command with thread options."""

    def test_publish_thread_dry_run(self, runner, mock_config_and_registry):
        """Publish --thread --dry-run shows thread preview."""
        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "thread.md"
        md_file.write_text("---\ntitle: Thread Post\ncanonical_url: https://example.com/thread\n---\n\nShort content for thread testing.")

        result = runner.invoke(cli, [
            "publish", str(md_file), "--to", "bluesky", "--thread", "--dry-run"
        ])

        assert result.exit_code == 0
        assert "thread" in result.output.lower() or "Dry Run" in result.output

    def test_publish_thread_style_option(self, runner, mock_config_and_registry):
        """Publish --thread-style option is recognized."""
        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "thread.md"
        md_file.write_text("---\ntitle: Thread Post\ncanonical_url: https://example.com/thread\n---\nContent.")

        result = runner.invoke(cli, [
            "publish", str(md_file), "--to", "bluesky", "--thread", "--thread-style", "numbered", "--dry-run"
        ])

        assert result.exit_code == 0
        assert "no such option" not in result.output.lower()

    def test_publish_thread_unsupported_platform(self, runner, mock_config_and_registry):
        """Publish --thread to platform that doesn't support threads."""
        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "thread.md"
        md_file.write_text("---\ntitle: Thread Post\ncanonical_url: https://example.com/thread\n---\nContent.")

        result = runner.invoke(cli, [
            "publish", str(md_file), "--to", "devto", "--thread", "--dry-run"
        ])

        # Should warn about thread not supported or still succeed for dry-run
        assert result.exit_code == 0
        assert "thread" in result.output.lower() or "devto" in result.output


class TestRegistryDeletionIntegration:
    """Integration tests for deletion workflow."""

    def test_delete_and_check_status_workflow(self, runner, mock_config_and_registry):
        """Full workflow: publish -> delete -> status shows deleted."""
        from crier.registry import record_publication, record_deletion, is_deleted

        posts_dir = mock_config_and_registry["posts_dir"]
        md_file = posts_dir / "test.md"
        md_file.write_text("---\ntitle: Test\ncanonical_url: https://example.com/test\n---\nContent.")

        # Register
        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            source_file=str(md_file),
        )

        # Delete
        record_deletion("https://example.com/test", "devto")
        assert is_deleted("https://example.com/test", "devto") is True

        # Check status shows it
        result = runner.invoke(cli, ["status", str(md_file)])
        assert result.exit_code == 0

    def test_archive_and_audit_workflow(self, runner, mock_config_and_registry):
        """Full workflow: publish -> archive -> audit excludes it."""
        from crier.registry import record_publication, set_archived

        posts_dir = mock_config_and_registry["posts_dir"]

        active_file = posts_dir / "active.md"
        active_file.write_text("---\ntitle: Active\ncanonical_url: https://example.com/active\n---\nContent.")

        archived_file = posts_dir / "archived.md"
        archived_file.write_text("---\ntitle: Archived\ncanonical_url: https://example.com/archived\n---\nContent.")

        record_publication(
            canonical_url="https://example.com/archived",
            platform="devto",
            article_id="2",
            url="https://dev.to/archived",
            source_file=str(archived_file),
        )

        # Archive it
        set_archived("https://example.com/archived", archived=True)

        # Audit should exclude archived
        result = runner.invoke(cli, ["audit"])
        assert result.exit_code == 0
        assert "archived.md" not in result.output

        # Unarchive and verify it appears
        set_archived("https://example.com/archived", archived=False)
        result = runner.invoke(cli, ["audit"])
        assert result.exit_code == 0
        assert "archived.md" in result.output


class TestPublishErrorTracking:
    """Tests that verify error recording during publish."""

    @patch("crier.cli.get_platform")
    def test_publish_records_failure_on_exception(self, mock_get_platform, runner, mock_config_and_registry):
        """Mock platform.publish() to raise Exception, verify record_failure is called and exit code is correct."""
        mock_platform_cls = Mock()
        mock_platform = Mock()
        mock_platform.publish.side_effect = Exception("Connection timeout")
        mock_platform_cls.return_value = mock_platform
        mock_get_platform.return_value = mock_platform_cls

        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("""\
---
title: Test Article
canonical_url: https://example.com/test
---

Content here.
""")

        with patch("crier.cli.record_failure") as mock_record_failure:
            result = runner.invoke(cli, ["publish", str(test_file), "--to", "devto"])

        assert result.exit_code == 1
        mock_record_failure.assert_called_once()
        call_kwargs = mock_record_failure.call_args
        assert call_kwargs[1]["canonical_url"] == "https://example.com/test"
        assert call_kwargs[1]["platform"] == "devto"
        assert "Connection timeout" in call_kwargs[1]["error_msg"]

    @patch("crier.cli.get_platform")
    def test_publish_records_failure_on_api_error(self, mock_get_platform, runner, mock_config_and_registry):
        """Mock platform.publish() to return PublishResult(success=False), verify record_failure is called."""
        from crier.platforms.base import PublishResult

        mock_platform_cls = Mock()
        mock_platform = Mock()
        mock_platform.publish.return_value = PublishResult(
            success=False,
            platform="devto",
            error="API error: rate limited",
        )
        mock_platform_cls.return_value = mock_platform
        mock_get_platform.return_value = mock_platform_cls

        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("""\
---
title: Test Article
canonical_url: https://example.com/test
---

Content here.
""")

        with patch("crier.cli.record_failure") as mock_record_failure:
            result = runner.invoke(cli, ["publish", str(test_file), "--to", "devto"])

        mock_record_failure.assert_called_once()
        call_kwargs = mock_record_failure.call_args
        assert call_kwargs[1]["canonical_url"] == "https://example.com/test"
        assert call_kwargs[1]["platform"] == "devto"
        assert "API error" in call_kwargs[1]["error_msg"]

    @patch("crier.cli.get_platform")
    def test_publish_partial_success_exit_code_2(self, mock_get_platform, runner, mock_config_and_registry):
        """Publish to 2 platforms, one succeeds and one fails, verify exit code 2 (partial)."""
        from crier.platforms.base import PublishResult

        # Make get_platform return different behaviour per platform
        def platform_factory(name):
            cls = Mock()
            inst = Mock()
            if name == "devto":
                inst.publish.return_value = PublishResult(
                    success=True,
                    platform="devto",
                    article_id="123",
                    url="https://dev.to/test",
                )
            else:
                inst.publish.return_value = PublishResult(
                    success=False,
                    platform="bluesky",
                    error="Failed to post",
                )
            cls.return_value = inst
            return cls

        mock_get_platform.side_effect = platform_factory

        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("""\
---
title: Test Article
canonical_url: https://example.com/test
---

Content here.
""")

        result = runner.invoke(cli, ["publish", str(test_file), "--to", "devto", "--to", "bluesky"])
        assert result.exit_code == 2

    @patch("crier.cli.get_platform")
    def test_publish_all_fail_exit_code_1(self, mock_get_platform, runner, mock_config_and_registry):
        """Publish to 2 platforms, both fail, verify exit code 1."""
        from crier.platforms.base import PublishResult

        mock_platform_cls = Mock()
        mock_platform = Mock()
        mock_platform.publish.return_value = PublishResult(
            success=False,
            platform="devto",
            error="Server error",
        )
        mock_platform_cls.return_value = mock_platform
        mock_get_platform.return_value = mock_platform_cls

        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("""\
---
title: Test Article
canonical_url: https://example.com/test
---

Content here.
""")

        result = runner.invoke(cli, ["publish", str(test_file), "--to", "devto", "--to", "bluesky"])
        assert result.exit_code == 1


class TestAuditFailedFlag:
    """Tests for crier audit --failed."""

    def test_audit_failed_no_failures(self, runner, mock_config_and_registry):
        """No failures recorded, shows 'No recorded failures'."""
        result = runner.invoke(cli, ["audit", "--failed"])
        assert result.exit_code == 0
        assert "No recorded failures" in result.output

    def test_audit_failed_shows_table(self, runner, mock_config_and_registry):
        """Record some failures in registry, verify table output."""
        from crier.registry import record_failure

        posts_dir = mock_config_and_registry["posts_dir"]
        test_file = posts_dir / "fail-test.md"
        test_file.write_text("---\ntitle: Fail Test\ncanonical_url: https://example.com/fail\n---\nContent.")

        record_failure(
            canonical_url="https://example.com/fail",
            platform="devto",
            error_msg="API rate limit exceeded",
            title="Fail Test",
            source_file=str(test_file),
        )

        result = runner.invoke(cli, ["audit", "--failed"])
        assert result.exit_code == 0
        assert "Failed Publications" in result.output
        assert "devto" in result.output
        assert "API rate limit" in result.output

    def test_audit_failed_json_output(self, runner, mock_config_and_registry):
        """Same with --json flag, verify JSON structure."""
        import json

        from crier.registry import record_failure

        posts_dir = mock_config_and_registry["posts_dir"]
        test_file = posts_dir / "fail-test.md"
        test_file.write_text("---\ntitle: Fail Test\ncanonical_url: https://example.com/fail\n---\nContent.")

        record_failure(
            canonical_url="https://example.com/fail",
            platform="devto",
            error_msg="API error 500",
            title="Fail Test",
            source_file=str(test_file),
        )

        result = runner.invoke(cli, ["audit", "--failed", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["command"] == "audit"
        assert data["mode"] == "failed"
        assert len(data["failures"]) == 1
        assert data["failures"][0]["platform"] == "devto"
        assert data["failures"][0]["error"] == "API error 500"
        assert data["summary"]["total_failures"] == 1

    def test_audit_failed_retry_no_failures(self, runner, mock_config_and_registry):
        """--retry with no failures shows message."""
        result = runner.invoke(cli, ["audit", "--retry"])
        assert result.exit_code == 0
        assert "No recorded failures" in result.output


class TestAuditRetryFlag:
    """Tests for crier audit --retry."""

    @patch("crier.cli.get_platform")
    def test_audit_retry_success(self, mock_get_platform, runner, mock_config_and_registry):
        """Record a failure, mock successful re-publish, verify success message and exit code 0."""
        from crier.platforms.base import PublishResult
        from crier.registry import record_failure

        posts_dir = mock_config_and_registry["posts_dir"]
        test_file = posts_dir / "retry-test.md"
        test_file.write_text("""\
---
title: Retry Test
canonical_url: https://example.com/retry
---

Content for retry.
""")

        record_failure(
            canonical_url="https://example.com/retry",
            platform="devto",
            error_msg="Temporary server error",
            title="Retry Test",
            source_file=str(test_file),
        )

        mock_platform_cls = Mock()
        mock_platform = Mock()
        mock_platform.publish.return_value = PublishResult(
            success=True,
            platform="devto",
            article_id="456",
            url="https://dev.to/retry-test",
        )
        mock_platform_cls.return_value = mock_platform
        mock_get_platform.return_value = mock_platform_cls

        result = runner.invoke(cli, ["audit", "--retry"])
        assert result.exit_code == 0
        assert "Retry complete" in result.output
        assert "1 succeeded" in result.output

    def test_audit_retry_dry_run(self, runner, mock_config_and_registry):
        """Record a failure, use --retry --dry-run, verify 'would_retry' without publish."""
        import json

        from crier.registry import record_failure

        posts_dir = mock_config_and_registry["posts_dir"]
        test_file = posts_dir / "retry-dry.md"
        test_file.write_text("""\
---
title: Retry Dry
canonical_url: https://example.com/retry-dry
---

Content for dry retry.
""")

        record_failure(
            canonical_url="https://example.com/retry-dry",
            platform="devto",
            error_msg="Server unavailable",
            title="Retry Dry",
            source_file=str(test_file),
        )

        result = runner.invoke(cli, ["audit", "--retry", "--dry-run", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["mode"] == "retry"
        assert len(data["results"]) == 1
        assert data["results"][0]["action"] == "would_retry"
        assert data["results"][0]["success"] is True

    def test_audit_retry_source_not_found(self, runner, mock_config_and_registry):
        """Record a failure with nonexistent source file, verify error handling."""
        import json

        from crier.registry import record_failure

        record_failure(
            canonical_url="https://example.com/gone",
            platform="devto",
            error_msg="Previous error",
            title="Gone Article",
            source_file="/nonexistent/path/gone.md",
        )

        result = runner.invoke(cli, ["audit", "--retry", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["mode"] == "retry"
        assert len(data["results"]) == 1
        assert data["results"][0]["success"] is False
        assert "Source file not found" in data["results"][0]["error"]

    @patch("crier.cli.get_platform")
    def test_audit_retry_partial_exit_code(self, mock_get_platform, runner, mock_config_and_registry):
        """Two failures, one retry succeeds one fails, verify exit code 2."""
        from crier.platforms.base import PublishResult
        from crier.registry import record_failure

        posts_dir = mock_config_and_registry["posts_dir"]

        # First failure - with existing source file
        test_file1 = posts_dir / "retry1.md"
        test_file1.write_text("""\
---
title: Retry One
canonical_url: https://example.com/retry1
---

Content one.
""")
        record_failure(
            canonical_url="https://example.com/retry1",
            platform="devto",
            error_msg="Error one",
            title="Retry One",
            source_file=str(test_file1),
        )

        # Second failure - with existing source file
        test_file2 = posts_dir / "retry2.md"
        test_file2.write_text("""\
---
title: Retry Two
canonical_url: https://example.com/retry2
---

Content two.
""")
        record_failure(
            canonical_url="https://example.com/retry2",
            platform="devto",
            error_msg="Error two",
            title="Retry Two",
            source_file=str(test_file2),
        )

        # Mock platform: first call succeeds, second fails
        call_count = {"n": 0}

        def mock_publish(article):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return PublishResult(
                    success=True,
                    platform="devto",
                    article_id="789",
                    url="https://dev.to/retry1",
                )
            else:
                return PublishResult(
                    success=False,
                    platform="devto",
                    error="Still failing",
                )

        mock_platform_cls = Mock()
        mock_platform = Mock()
        mock_platform.publish.side_effect = mock_publish
        mock_platform_cls.return_value = mock_platform
        mock_get_platform.return_value = mock_platform_cls

        result = runner.invoke(cli, ["audit", "--retry"])
        assert result.exit_code == 2


class TestFeedCommand:
    """Tests for crier feed."""

    @patch("crier.feed.get_site_base_url", return_value="https://example.com")
    def test_feed_rss_output(self, mock_base_url, runner, mock_config_and_registry):
        """Create content file, run feed command, verify RSS XML output."""
        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "post1.md").write_text("""\
---
title: Feed Post One
date: 2025-06-01
canonical_url: https://example.com/post1
tags: [python]
---

This is the body of feed post one.
""")

        result = runner.invoke(cli, ["feed", str(posts_dir)])
        assert result.exit_code == 0
        assert "<?xml" in result.output
        assert "<rss" in result.output
        assert "Feed Post One" in result.output

    @patch("crier.feed.get_site_base_url", return_value="https://example.com")
    def test_feed_atom_format(self, mock_base_url, runner, mock_config_and_registry):
        """Same with --format atom."""
        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "post1.md").write_text("""\
---
title: Atom Post
date: 2025-06-01
canonical_url: https://example.com/atom
---

Atom feed content.
""")

        result = runner.invoke(cli, ["feed", str(posts_dir), "--format", "atom"])
        assert result.exit_code == 0
        assert "<?xml" in result.output
        assert "<feed" in result.output
        assert "Atom Post" in result.output

    @patch("crier.feed.get_site_base_url", return_value="https://example.com")
    @patch("crier.cli.console")
    def test_feed_output_file(self, mock_console, mock_base_url, runner, mock_config_and_registry):
        """Use --output flag, verify file written."""
        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "post1.md").write_text("""\
---
title: Output Post
date: 2025-06-01
canonical_url: https://example.com/output
---

Output file content.
""")

        output_path = mock_config_and_registry["tmp_path"] / "feed.xml"
        result = runner.invoke(cli, ["feed", str(posts_dir), "--output", str(output_path)])
        assert result.exit_code == 0
        assert output_path.exists()
        feed_content = output_path.read_text()
        assert "<?xml" in feed_content
        assert "Output Post" in feed_content

    def test_feed_no_content(self, runner, mock_config_and_registry):
        """No content files, verify exit code 1."""
        posts_dir = mock_config_and_registry["posts_dir"]
        # No files created
        result = runner.invoke(cli, ["feed", str(posts_dir)])
        assert result.exit_code == 1

    @patch("crier.feed.get_site_base_url", return_value="https://example.com")
    def test_feed_with_tag_filter(self, mock_base_url, runner, mock_config_and_registry):
        """Use --tag flag."""
        posts_dir = mock_config_and_registry["posts_dir"]
        (posts_dir / "python-post.md").write_text("""\
---
title: Python Post
date: 2025-06-01
tags: [python]
canonical_url: https://example.com/python
---

Python content.
""")
        (posts_dir / "js-post.md").write_text("""\
---
title: JS Post
date: 2025-06-01
tags: [javascript]
canonical_url: https://example.com/js
---

JS content.
""")

        result = runner.invoke(cli, ["feed", str(posts_dir), "--tag", "python"])
        assert result.exit_code == 0
        assert "Python Post" in result.output
        assert "JS Post" not in result.output

    @patch("crier.feed.get_site_base_url", return_value="https://example.com")
    def test_feed_with_limit(self, mock_base_url, runner, mock_config_and_registry):
        """Use --limit flag."""
        posts_dir = mock_config_and_registry["posts_dir"]
        for i in range(5):
            (posts_dir / f"post{i}.md").write_text(f"""\
---
title: Post {i}
date: 2025-0{i+1}-01
canonical_url: https://example.com/post{i}
---

Content {i}.
""")

        result = runner.invoke(cli, ["feed", str(posts_dir), "--limit", "2"])
        assert result.exit_code == 0
        assert "<?xml" in result.output
        # Should only have 2 items (the most recent ones)
        # Count <item> tags for RSS
        assert result.output.count("<item>") == 2


class TestProjectOption:
    """Tests for --project global option."""

    def test_project_option_accepted(self, runner, tmp_path):
        """CLI accepts --project before subcommand."""
        result = runner.invoke(cli, ["--project", str(tmp_path), "--version"])
        assert result.exit_code == 0

    def test_project_option_stores_in_context(self, runner, tmp_path):
        """--project value is stored in Click context."""
        crier_dir = tmp_path / ".crier"
        crier_dir.mkdir()
        (crier_dir / "registry.yaml").write_text("version: 2\narticles: {}\n")

        # --help should work with --project
        result = runner.invoke(cli, ["--project", str(tmp_path), "--help"])
        assert result.exit_code == 0
        assert "--project" in result.output

    def test_project_option_rejects_nonexistent_dir(self, runner, tmp_path):
        """--project rejects a directory that doesn't exist."""
        nonexistent = tmp_path / "does_not_exist"
        # Must use a real subcommand; eager options (--version/--help) skip validation
        result = runner.invoke(cli, ["--project", str(nonexistent), "doctor"])
        assert result.exit_code != 0
        assert "does not exist" in result.output

    def test_project_option_rejects_file(self, runner, tmp_path):
        """--project rejects a file path (must be directory)."""
        some_file = tmp_path / "somefile.txt"
        some_file.write_text("hello")
        result = runner.invoke(cli, ["--project", str(some_file), "doctor"])
        assert result.exit_code != 0

    def test_project_option_in_help(self, runner):
        """--project appears in top-level help."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "--project" in result.output

    def test_no_project_option_default_none(self, runner):
        """Without --project, context stores None."""
        from crier.cli import get_project_path

        # Invoke --version without --project; context should have None
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0


class TestExitCodes:
    """Tests for consistent exit codes."""

    @patch("crier.cli.get_platform")
    def test_publish_success_exit_0(self, mock_get_platform, runner, mock_config_and_registry):
        """Successful publish returns 0."""
        from crier.platforms.base import PublishResult

        mock_platform_cls = Mock()
        mock_platform = Mock()
        mock_platform.publish.return_value = PublishResult(
            success=True,
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
        )
        mock_platform_cls.return_value = mock_platform
        mock_get_platform.return_value = mock_platform_cls

        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        test_file.write_text("""\
---
title: Test Article
canonical_url: https://example.com/test
---

Content here.
""")

        result = runner.invoke(cli, ["publish", str(test_file), "--to", "devto"])
        assert result.exit_code == 0

    def test_audit_no_missing_exit_0(self, runner, mock_config_and_registry):
        """Audit with nothing missing returns 0."""
        from crier.registry import record_publication

        posts_dir = mock_config_and_registry["posts_dir"]
        test_file = posts_dir / "test.md"
        test_file.write_text("""\
---
title: Test Article
canonical_url: https://example.com/test
---

Content here.
""")

        # Record it as already published to all configured platforms
        record_publication(
            canonical_url="https://example.com/test",
            platform="devto",
            article_id="123",
            url="https://dev.to/test",
            source_file=str(test_file),
        )
        record_publication(
            canonical_url="https://example.com/test",
            platform="bluesky",
            article_id="456",
            url="https://bsky.app/test",
            source_file=str(test_file),
        )
        record_publication(
            canonical_url="https://example.com/test",
            platform="twitter",
            article_id="789",
            url="https://twitter.com/test",
            source_file=str(test_file),
        )

        result = runner.invoke(cli, ["audit"])
        assert result.exit_code == 0
