"""Tests for crier.config module."""

import pytest
import yaml

from crier.config import (
    is_manual_mode_key,
    is_import_mode_key,
    is_platform_configured,
    is_short_form_platform,
    get_api_key,
    get_api_key_source,
    get_platform_mode,
    set_api_key,
    get_profile,
    set_profile,
    get_all_profiles,
    get_content_paths,
    set_content_paths,
    add_content_path,
    remove_content_path,
    load_config,
    load_global_config,
    save_config,
    get_config_path,
    get_site_root,
    get_project_root,
    get_llm_config,
    set_llm_config,
    is_llm_configured,
    get_llm_temperature,
    get_llm_retry_count,
    get_llm_truncate_fallback,
    get_check_overrides,
    get_exclude_patterns,
    set_exclude_patterns,
    get_file_extensions,
    set_file_extensions,
    get_site_base_url,
    set_site_base_url,
    infer_canonical_url,
    get_default_profile,
    set_default_profile,
    get_rewrite_author,
    set_rewrite_author,
    DEFAULT_EXCLUDE_PATTERNS,
    DEFAULT_FILE_EXTENSIONS,
    SHORT_FORM_PLATFORMS,
)


class TestIsManualModeKey:
    """Tests for is_manual_mode_key()."""

    def test_none_returns_false(self):
        assert is_manual_mode_key(None) is False

    def test_empty_string_returns_false(self):
        assert is_manual_mode_key("") is False

    def test_manual_lowercase_returns_true(self):
        assert is_manual_mode_key("manual") is True

    def test_manual_uppercase_returns_true(self):
        assert is_manual_mode_key("MANUAL") is True

    def test_manual_mixed_case_returns_true(self):
        assert is_manual_mode_key("Manual") is True
        assert is_manual_mode_key("MaNuAl") is True

    def test_real_api_key_returns_false(self):
        assert is_manual_mode_key("abc123xyz") is False
        assert is_manual_mode_key("handle.bsky.social:app-password") is False


class TestIsPlatformConfigured:
    """Tests for is_platform_configured()."""

    def test_unconfigured_platform(self, tmp_config):
        assert is_platform_configured("nonexistent") is False

    def test_configured_with_real_key(self, configured_platforms):
        assert is_platform_configured("devto") is True

    def test_configured_with_manual_key(self, configured_platforms):
        assert is_platform_configured("twitter") is True

    def test_configured_with_empty_key(self, configured_platforms):
        # Empty string key means it's in config but empty
        assert is_platform_configured("linkedin") is True

    def test_env_var_takes_precedence(self, tmp_config, mock_env_api_key):
        mock_env_api_key("testplatform", "env_key")
        assert is_platform_configured("testplatform") is True


class TestGetApiKey:
    """Tests for get_api_key()."""

    def test_returns_none_for_unconfigured(self, tmp_config):
        assert get_api_key("nonexistent") is None

    def test_returns_key_from_config(self, configured_platforms):
        assert get_api_key("devto") == "devto_test_key"

    def test_returns_manual_key(self, configured_platforms):
        assert get_api_key("twitter") == "manual"

    def test_env_var_overrides_config(self, configured_platforms, mock_env_api_key):
        mock_env_api_key("devto", "env_override_key")
        assert get_api_key("devto") == "env_override_key"

    def test_env_var_for_unconfigured_platform(self, tmp_config, mock_env_api_key):
        mock_env_api_key("newplatform", "env_key")
        assert get_api_key("newplatform") == "env_key"


class TestSetApiKey:
    """Tests for set_api_key()."""

    def test_set_new_key(self, tmp_config):
        set_api_key("testplatform", "test_key_123")
        assert get_api_key("testplatform") == "test_key_123"

    def test_update_existing_key(self, configured_platforms):
        set_api_key("devto", "new_key")
        assert get_api_key("devto") == "new_key"


class TestProfiles:
    """Tests for profile management."""

    def test_get_nonexistent_profile(self, tmp_config):
        assert get_profile("nonexistent") is None

    def test_get_simple_profile(self, configured_platforms):
        profile = get_profile("blogs")
        assert profile == ["devto", "hashnode"]

    def test_get_nested_profile(self, configured_platforms):
        # "all" references "blogs" and "social"
        profile = get_profile("all")
        assert "devto" in profile
        assert "hashnode" in profile
        assert "bluesky" in profile
        assert "mastodon" in profile

    def test_set_profile(self, tmp_config):
        set_profile("myprofile", ["platform1", "platform2"])
        assert get_profile("myprofile") == ["platform1", "platform2"]

    def test_get_all_profiles(self, configured_platforms):
        profiles = get_all_profiles()
        assert "blogs" in profiles
        assert "social" in profiles
        assert "all" in profiles


class TestContentPaths:
    """Tests for content path management."""

    def test_empty_content_paths(self, tmp_config):
        assert get_content_paths() == []

    def test_get_content_paths(self, configured_platforms):
        paths = get_content_paths()
        assert "posts" in paths
        assert "articles" in paths

    def test_set_content_paths(self, tmp_config):
        set_content_paths(["content", "blog"])
        paths = get_content_paths()
        assert paths == ["content", "blog"]

    def test_add_content_path(self, tmp_config):
        add_content_path("posts")
        add_content_path("articles")
        paths = get_content_paths()
        assert "posts" in paths
        assert "articles" in paths

    def test_add_duplicate_path(self, tmp_config):
        add_content_path("posts")
        add_content_path("posts")  # Adding same path again
        paths = get_content_paths()
        assert paths.count("posts") == 1

    def test_remove_content_path(self, configured_platforms):
        assert remove_content_path("posts") is True
        paths = get_content_paths()
        assert "posts" not in paths

    def test_remove_nonexistent_path(self, tmp_config):
        assert remove_content_path("nonexistent") is False


class TestLoadConfig:
    """Tests for load_config() — global only, no merge."""

    def test_load_empty_config(self, tmp_config):
        config = load_config()
        assert config == {}

    def test_load_config_with_platforms(self, configured_platforms):
        config = load_config()
        assert "platforms" in config
        assert "devto" in config["platforms"]

    def test_load_config_returns_all_keys(self, tmp_config):
        """All config keys are read from the single global file."""
        config_data = {
            "content_paths": ["content"],
            "site_base_url": "https://example.com",
            "platforms": {"devto": {"api_key": "key"}},
            "profiles": {"blogs": ["devto"]},
        }
        tmp_config.write_text(yaml.dump(config_data))

        config = load_config()
        assert config["content_paths"] == ["content"]
        assert config["site_base_url"] == "https://example.com"
        assert config["platforms"]["devto"]["api_key"] == "key"

    def test_load_global_config_is_alias(self, configured_platforms):
        """load_global_config() is an alias for load_config()."""
        assert load_config() == load_global_config()


class TestSaveConfig:
    """Tests for save_config()."""

    def test_creates_config_dir(self, tmp_path, monkeypatch):
        config_dir = tmp_path / "new_config_dir"
        config_file = config_dir / "config.yaml"
        monkeypatch.setattr("crier.config.DEFAULT_CONFIG_FILE", config_file)
        monkeypatch.setattr("crier.config.DEFAULT_CONFIG_DIR", config_dir)
        monkeypatch.delenv("CRIER_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)

        save_config({"test": "value"})
        assert config_file.exists()
        with open(config_file) as f:
            data = yaml.safe_load(f)
        assert data["test"] == "value"


class TestConfigPaths:
    """Tests for get_config_path."""

    def test_get_config_path_default(self, tmp_config):
        path = get_config_path()
        assert path == tmp_config

    def test_get_config_path_env_override(self, tmp_path, monkeypatch):
        custom_path = tmp_path / "custom_config.yaml"
        monkeypatch.setenv("CRIER_CONFIG", str(custom_path))
        assert get_config_path() == custom_path


class TestSiteRoot:
    """Tests for get_site_root() and get_project_root()."""

    def test_get_site_root_returns_path(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        site = tmp_path / "mysite"
        site.mkdir()
        config_file.write_text(yaml.dump({"site_root": str(site)}))
        monkeypatch.setenv("CRIER_CONFIG", str(config_file))
        result = get_site_root()
        assert result == site.resolve()

    def test_get_site_root_expands_tilde(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"site_root": "~/mysite"}))
        monkeypatch.setenv("CRIER_CONFIG", str(config_file))
        from pathlib import Path
        result = get_site_root()
        assert result == (Path.home() / "mysite").resolve()

    def test_get_site_root_returns_none_when_unset(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"platforms": {}}))
        monkeypatch.setenv("CRIER_CONFIG", str(config_file))
        assert get_site_root() is None

    def test_get_project_root_uses_site_root(self, tmp_path, monkeypatch):
        site = tmp_path / "mysite"
        site.mkdir()
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"site_root": str(site)}))
        monkeypatch.setenv("CRIER_CONFIG", str(config_file))
        assert get_project_root() == site.resolve()

    def test_get_project_root_falls_back_to_cwd(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({}))
        monkeypatch.setenv("CRIER_CONFIG", str(config_file))
        monkeypatch.chdir(tmp_path)
        assert get_project_root() == tmp_path.resolve()


class TestGlobalOnlyConfig:
    """Config is global-only — no local config, no merge logic."""

    def test_getters_read_from_global(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "site_base_url": "https://example.com",
            "exclude_patterns": ["_index.md"],
            "file_extensions": [".md"],
            "default_profile": "blogs",
            "rewrite_author": "claude-code",
        }))
        monkeypatch.setenv("CRIER_CONFIG", str(config_file))
        assert get_site_base_url() == "https://example.com"
        assert get_exclude_patterns() == ["_index.md"]
        assert get_file_extensions() == [".md"]
        assert get_default_profile() == "blogs"
        assert get_rewrite_author() == "claude-code"

    def test_setters_write_to_global(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"platforms": {}}))
        monkeypatch.setenv("CRIER_CONFIG", str(config_file))
        set_site_base_url("https://new.com")
        cfg = yaml.safe_load(config_file.read_text())
        assert cfg["site_base_url"] == "https://new.com"
        # Other keys preserved
        assert "platforms" in cfg

    def test_setters_preserve_existing_keys(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "platforms": {"devto": {"api_key": "key"}},
            "content_paths": ["content"],
        }))
        monkeypatch.setenv("CRIER_CONFIG", str(config_file))
        set_exclude_patterns(["_index.md"])
        cfg = yaml.safe_load(config_file.read_text())
        assert cfg["exclude_patterns"] == ["_index.md"]
        assert cfg["platforms"]["devto"]["api_key"] == "key"
        assert cfg["content_paths"] == ["content"]

    def test_check_overrides_from_global(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "checks": {
                "missing-tags": "disabled",
                "missing-date": "error",
            }
        }))
        monkeypatch.setenv("CRIER_CONFIG", str(config_file))
        overrides = get_check_overrides()
        assert overrides["missing-tags"] == "disabled"
        assert overrides["missing-date"] == "error"


class TestIsImportModeKey:
    """Tests for is_import_mode_key()."""

    def test_none_returns_false(self):
        assert is_import_mode_key(None) is False

    def test_empty_string_returns_false(self):
        assert is_import_mode_key("") is False

    def test_import_lowercase(self):
        assert is_import_mode_key("import") is True

    def test_import_uppercase(self):
        assert is_import_mode_key("IMPORT") is True

    def test_import_mixed_case(self):
        assert is_import_mode_key("Import") is True

    def test_real_key_returns_false(self):
        assert is_import_mode_key("sk-abc123") is False

    def test_manual_returns_false(self):
        assert is_import_mode_key("manual") is False


class TestGetPlatformMode:
    """Tests for get_platform_mode()."""

    def test_unconfigured_platform(self, tmp_config):
        assert get_platform_mode("nonexistent") == "unconfigured"

    def test_api_mode(self, configured_platforms):
        assert get_platform_mode("devto") == "api"

    def test_manual_mode(self, configured_platforms):
        assert get_platform_mode("twitter") == "manual"

    def test_import_mode(self, tmp_config):
        set_api_key("medium", "import")
        assert get_platform_mode("medium") == "import"

    def test_env_var_api_mode(self, tmp_config, mock_env_api_key):
        mock_env_api_key("devto", "real_key_from_env")
        assert get_platform_mode("devto") == "api"


class TestGetApiKeySource:
    """Tests for get_api_key_source()."""

    def test_returns_none_when_unset(self, tmp_config):
        assert get_api_key_source("nonexistent") is None

    def test_returns_env_when_from_env(self, tmp_config, mock_env_api_key):
        mock_env_api_key("devto", "from_env")
        assert get_api_key_source("devto") == "env"

    def test_returns_global_when_from_config(self, configured_platforms):
        assert get_api_key_source("devto") == "global"

    def test_env_takes_precedence_over_config(self, configured_platforms, mock_env_api_key):
        mock_env_api_key("devto", "env_key")
        assert get_api_key_source("devto") == "env"

    def test_returns_none_for_empty_key(self, tmp_config):
        # Platform with empty api_key in config -- get_api_key_source
        # checks truthiness, empty string is falsy
        config = {"platforms": {"test": {"api_key": ""}}}
        tmp_config.write_text(yaml.dump(config))
        assert get_api_key_source("test") is None


class TestIsShortFormPlatform:
    """Tests for is_short_form_platform()."""

    def test_short_form_platforms(self):
        assert is_short_form_platform("bluesky") is True
        assert is_short_form_platform("mastodon") is True
        assert is_short_form_platform("twitter") is True
        assert is_short_form_platform("threads") is True

    def test_long_form_platforms(self):
        assert is_short_form_platform("devto") is False
        assert is_short_form_platform("hashnode") is False
        assert is_short_form_platform("medium") is False

    def test_short_form_platforms_constant(self):
        assert SHORT_FORM_PLATFORMS == {"bluesky", "mastodon", "twitter", "threads"}


class TestLLMConfig:
    """Tests for LLM configuration get/set."""

    def test_get_llm_config_empty(self, tmp_config, monkeypatch):
        """No LLM config returns empty dict."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        config = get_llm_config()
        assert config == {}

    def test_set_and_get_llm_config_api_key(self, tmp_config, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        set_llm_config(api_key="sk-test123")
        config = get_llm_config()
        assert config["api_key"] == "sk-test123"
        # Defaults should be applied when api_key is present
        assert config["base_url"] == "https://api.openai.com/v1"
        assert config["model"] == "gpt-4o-mini"

    def test_set_llm_config_custom_base_url(self, tmp_config, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        set_llm_config(api_key="key", base_url="http://localhost:11434/v1")
        config = get_llm_config()
        assert config["base_url"] == "http://localhost:11434/v1"

    def test_set_llm_config_custom_model(self, tmp_config, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        set_llm_config(api_key="key", model="llama3")
        config = get_llm_config()
        assert config["model"] == "llama3"

    def test_set_llm_config_provider(self, tmp_config, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        set_llm_config(provider="ollama")
        config = get_llm_config()
        assert config["provider"] == "ollama"

    def test_set_llm_config_rewrite_prompt(self, tmp_config, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        set_llm_config(rewrite_prompt="Summarize this content")
        config = get_llm_config()
        assert config["rewrite_prompt"] == "Summarize this content"

    def test_set_llm_config_partial_update(self, tmp_config, monkeypatch):
        """Setting one field does not clear others."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        set_llm_config(api_key="sk-test", model="gpt-4o")
        set_llm_config(temperature=0.9)
        config = get_llm_config()
        assert config["api_key"] == "sk-test"
        assert config["model"] == "gpt-4o"
        assert config["temperature"] == 0.9

    def test_set_llm_config_none_values_ignored(self, tmp_config, monkeypatch):
        """None values are not written to config."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        set_llm_config(api_key="sk-test")
        set_llm_config(model=None, temperature=None)
        config = get_llm_config()
        # Model should be defaulted, not set to None
        assert config["model"] == "gpt-4o-mini"

    def test_env_openai_api_key_overrides_config(self, tmp_config, monkeypatch):
        """OPENAI_API_KEY env var overrides config file."""
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        set_llm_config(api_key="config_key")
        monkeypatch.setenv("OPENAI_API_KEY", "env_key")
        config = get_llm_config()
        assert config["api_key"] == "env_key"

    def test_env_openai_base_url_overrides_config(self, tmp_config, monkeypatch):
        """OPENAI_BASE_URL env var overrides config file."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        set_llm_config(api_key="key", base_url="http://config-url/v1")
        monkeypatch.setenv("OPENAI_BASE_URL", "http://env-url/v1")
        config = get_llm_config()
        assert config["base_url"] == "http://env-url/v1"

    def test_env_openai_api_key_triggers_defaults(self, tmp_config, monkeypatch):
        """OPENAI_API_KEY alone triggers default base_url and model."""
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-only")
        config = get_llm_config()
        assert config["api_key"] == "sk-env-only"
        assert config["base_url"] == "https://api.openai.com/v1"
        assert config["model"] == "gpt-4o-mini"

    def test_no_defaults_without_api_key(self, tmp_config, monkeypatch):
        """Without api_key, no default base_url or model is set."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        set_llm_config(model="llama3")
        config = get_llm_config()
        assert "base_url" not in config or config.get("base_url") is None
        assert config["model"] == "llama3"


class TestIsLLMConfigured:
    """Tests for is_llm_configured()."""

    def test_not_configured_empty(self, tmp_config, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        assert is_llm_configured() is False

    def test_configured_with_api_key(self, tmp_config, monkeypatch):
        """API key triggers defaults for base_url and model."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        set_llm_config(api_key="sk-test")
        assert is_llm_configured() is True

    def test_configured_with_base_url_and_model(self, tmp_config, monkeypatch):
        """Direct base_url + model is sufficient (e.g., Ollama no key)."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        set_llm_config(base_url="http://localhost:11434/v1", model="llama3")
        assert is_llm_configured() is True

    def test_not_configured_model_only(self, tmp_config, monkeypatch):
        """Model alone is not sufficient -- needs base_url."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        set_llm_config(model="llama3")
        assert is_llm_configured() is False

    def test_configured_via_env_var(self, tmp_config, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
        assert is_llm_configured() is True


class TestLLMTemperature:
    """Tests for get_llm_temperature()."""

    def test_default_temperature(self, tmp_config, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        assert get_llm_temperature() == 0.7

    def test_custom_temperature(self, tmp_config, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        set_llm_config(api_key="key", temperature=1.2)
        assert get_llm_temperature() == 1.2

    def test_zero_temperature(self, tmp_config, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        set_llm_config(api_key="key", temperature=0.0)
        assert get_llm_temperature() == 0.0

    def test_temperature_returns_float(self, tmp_config, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        result = get_llm_temperature()
        assert isinstance(result, float)


class TestLLMRetryCount:
    """Tests for get_llm_retry_count()."""

    def test_default_retry_count(self, tmp_config, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        assert get_llm_retry_count() == 0

    def test_custom_retry_count(self, tmp_config, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        set_llm_config(api_key="key", retry_count=3)
        assert get_llm_retry_count() == 3

    def test_retry_count_returns_int(self, tmp_config, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        result = get_llm_retry_count()
        assert isinstance(result, int)


class TestLLMTruncateFallback:
    """Tests for get_llm_truncate_fallback()."""

    def test_default_truncate_fallback(self, tmp_config, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        assert get_llm_truncate_fallback() is False

    def test_enabled_truncate_fallback(self, tmp_config, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        set_llm_config(api_key="key", truncate_fallback=True)
        assert get_llm_truncate_fallback() is True

    def test_disabled_truncate_fallback(self, tmp_config, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        set_llm_config(api_key="key", truncate_fallback=False)
        assert get_llm_truncate_fallback() is False

    def test_returns_bool(self, tmp_config, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        result = get_llm_truncate_fallback()
        assert isinstance(result, bool)


class TestCheckOverrides:
    """Tests for get_check_overrides() -- severity overrides in config."""

    def test_empty_overrides(self, tmp_config):
        assert get_check_overrides() == {}

    def test_check_overrides_from_global_config(self, tmp_config):
        config = {
            "checks": {
                "missing-tags": "disabled",
                "missing-date": "error",
                "short-body": "disabled",
            }
        }
        tmp_config.write_text(yaml.dump(config))

        overrides = get_check_overrides()
        assert overrides["missing-tags"] == "disabled"
        assert overrides["missing-date"] == "error"
        assert overrides["short-body"] == "disabled"

    def test_single_override(self, tmp_config):
        tmp_config.write_text(yaml.dump({"checks": {"missing-title": "warning"}}))
        overrides = get_check_overrides()
        assert overrides == {"missing-title": "warning"}


class TestExcludePatterns:
    """Tests for get_exclude_patterns() and set_exclude_patterns()."""

    def test_empty_by_default(self, tmp_config):
        assert get_exclude_patterns() == []

    def test_set_and_get_exclude_patterns(self, tmp_config):
        set_exclude_patterns(["_index.md", "draft-*"])
        patterns = get_exclude_patterns()
        assert "_index.md" in patterns
        assert "draft-*" in patterns

    def test_overwrite_exclude_patterns(self, tmp_config):
        set_exclude_patterns(["_index.md"])
        set_exclude_patterns(["draft-*"])
        patterns = get_exclude_patterns()
        assert patterns == ["draft-*"]

    def test_default_exclude_patterns_constant(self):
        assert DEFAULT_EXCLUDE_PATTERNS == ["_index.md"]


class TestFileExtensions:
    """Tests for get_file_extensions() and set_file_extensions()."""

    def test_empty_by_default(self, tmp_config):
        assert get_file_extensions() == []

    def test_set_and_get_file_extensions(self, tmp_config):
        set_file_extensions([".md", ".mdx"])
        exts = get_file_extensions()
        assert ".md" in exts
        assert ".mdx" in exts

    def test_normalizes_extensions_with_dot(self, tmp_config):
        """Extensions without leading dot get normalized."""
        set_file_extensions(["md", "mdx"])
        exts = get_file_extensions()
        assert exts == [".md", ".mdx"]

    def test_already_dotted_extensions_unchanged(self, tmp_config):
        set_file_extensions([".md"])
        exts = get_file_extensions()
        assert exts == [".md"]

    def test_default_file_extensions_constant(self):
        assert DEFAULT_FILE_EXTENSIONS == [".md"]


class TestSiteBaseUrl:
    """Tests for get_site_base_url() and set_site_base_url()."""

    def test_none_by_default(self, tmp_config):
        assert get_site_base_url() is None

    def test_set_and_get(self, tmp_config):
        set_site_base_url("https://example.com")
        assert get_site_base_url() == "https://example.com"

    def test_trailing_slash_removed(self, tmp_config):
        set_site_base_url("https://example.com/")
        assert get_site_base_url() == "https://example.com"

    def test_multiple_trailing_slashes_removed(self, tmp_config):
        set_site_base_url("https://example.com///")
        assert get_site_base_url() == "https://example.com"


class TestInferCanonicalUrl:
    """Tests for infer_canonical_url()."""

    def test_index_md(self, tmp_path):
        content_root = tmp_path / "content"
        content_root.mkdir()
        file_path = content_root / "post" / "my-slug" / "index.md"
        file_path.parent.mkdir(parents=True)
        file_path.touch()

        url = infer_canonical_url(file_path, content_root, "https://example.com")
        assert url == "https://example.com/post/my-slug/"

    def test_underscore_index_md(self, tmp_path):
        content_root = tmp_path / "content"
        content_root.mkdir()
        file_path = content_root / "about" / "_index.md"
        file_path.parent.mkdir(parents=True)
        file_path.touch()

        url = infer_canonical_url(file_path, content_root, "https://example.com")
        assert url == "https://example.com/about/"

    def test_plain_md_file(self, tmp_path):
        content_root = tmp_path / "content"
        content_root.mkdir()
        file_path = content_root / "my-post.md"
        file_path.touch()

        url = infer_canonical_url(file_path, content_root, "https://example.com")
        assert url == "https://example.com/my-post/"

    def test_file_outside_content_root(self, tmp_path):
        content_root = tmp_path / "content"
        content_root.mkdir()
        file_path = tmp_path / "other" / "article.md"
        file_path.parent.mkdir(parents=True)
        file_path.touch()

        url = infer_canonical_url(file_path, content_root, "https://example.com")
        assert url == "https://example.com/article/"


class TestDefaultProfile:
    """Tests for get_default_profile() and set_default_profile()."""

    def test_none_by_default(self, tmp_config):
        assert get_default_profile() is None

    def test_set_and_get(self, tmp_config):
        set_default_profile("blogs")
        assert get_default_profile() == "blogs"


class TestRewriteAuthor:
    """Tests for get_rewrite_author() and set_rewrite_author()."""

    def test_none_by_default(self, tmp_config):
        assert get_rewrite_author() is None

    def test_set_and_get(self, tmp_config):
        set_rewrite_author("claude-code")
        assert get_rewrite_author() == "claude-code"


class TestEnvironmentVariableOverrides:
    """Tests for environment variable overrides across different config functions."""

    def test_crier_platform_api_key_env_override(self, tmp_config, monkeypatch):
        """CRIER_{PLATFORM}_API_KEY env overrides config file."""
        set_api_key("devto", "config_key")
        monkeypatch.setenv("CRIER_DEVTO_API_KEY", "env_key")
        assert get_api_key("devto") == "env_key"

    def test_crier_env_key_uppercase(self, tmp_config, monkeypatch):
        """Platform name is uppercased for env var lookup."""
        monkeypatch.setenv("CRIER_BLUESKY_API_KEY", "bsky_env")
        assert get_api_key("bluesky") == "bsky_env"

    def test_crier_config_env_var(self, tmp_path, monkeypatch):
        """CRIER_CONFIG env var overrides default config path."""
        custom_config = tmp_path / "custom.yaml"
        custom_config.write_text(yaml.dump({"platforms": {"devto": {"api_key": "custom_key"}}}))
        monkeypatch.setenv("CRIER_CONFIG", str(custom_config))

        assert get_api_key("devto") == "custom_key"

    def test_openai_api_key_for_llm(self, tmp_config, monkeypatch):
        """OPENAI_API_KEY sets LLM api_key with defaults."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-test")
        config = get_llm_config()
        assert config["api_key"] == "sk-env-test"
        assert config["base_url"] == "https://api.openai.com/v1"
        assert config["model"] == "gpt-4o-mini"

    def test_openai_base_url_for_llm(self, tmp_config, monkeypatch):
        """OPENAI_BASE_URL overrides LLM base_url."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
        config = get_llm_config()
        assert config["base_url"] == "http://localhost:11434/v1"

    def test_env_vars_cleared_do_not_interfere(self, tmp_config, monkeypatch):
        """Ensure no leftover env vars from other tests."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("CRIER_DEVTO_API_KEY", raising=False)
        config = get_llm_config()
        assert config == {}
        assert get_api_key("devto") is None


class TestContentPathManipulation:
    """Extended tests for add_content_path and remove_content_path."""

    def test_add_multiple_distinct_paths(self, tmp_config):
        add_content_path("posts")
        add_content_path("articles")
        add_content_path("pages")
        paths = get_content_paths()
        assert paths == ["posts", "articles", "pages"]

    def test_add_then_remove(self, tmp_config):
        add_content_path("posts")
        add_content_path("articles")
        remove_content_path("posts")
        paths = get_content_paths()
        assert paths == ["articles"]

    def test_remove_from_empty(self, tmp_config):
        assert remove_content_path("anything") is False

    def test_add_preserves_order(self, tmp_config):
        add_content_path("c")
        add_content_path("a")
        add_content_path("b")
        paths = get_content_paths()
        assert paths == ["c", "a", "b"]

    def test_remove_last_path(self, tmp_config):
        add_content_path("only")
        assert remove_content_path("only") is True
        assert get_content_paths() == []


class TestNetworkConfig:
    """Tests for network retry/timeout configuration."""

    def test_defaults(self, tmp_config):
        from crier.config import (
            get_network_retry_count,
            get_network_retry_backoff,
            get_network_timeout,
        )
        assert get_network_retry_count() == 3
        assert get_network_retry_backoff() == 1.0
        assert get_network_timeout() == 30

    def test_set_and_get(self, tmp_config):
        from crier.config import (
            set_network_config,
            get_network_retry_count,
            get_network_retry_backoff,
            get_network_timeout,
        )
        set_network_config(retry_count=5, retry_backoff=2.0, timeout=60)
        assert get_network_retry_count() == 5
        assert get_network_retry_backoff() == 2.0
        assert get_network_timeout() == 60

    def test_partial_update(self, tmp_config):
        from crier.config import (
            set_network_config,
            get_network_retry_count,
            get_network_timeout,
        )
        set_network_config(retry_count=1)
        assert get_network_retry_count() == 1
        assert get_network_timeout() == 30  # unchanged default

    def test_get_network_config_empty(self, tmp_config):
        from crier.config import get_network_config
        assert get_network_config() == {}
