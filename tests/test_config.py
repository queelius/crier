"""Tests for crier.config module."""

import pytest
import yaml

from crier.config import (
    is_manual_mode_key,
    is_platform_configured,
    get_api_key,
    set_api_key,
    get_profile,
    set_profile,
    get_all_profiles,
    get_content_paths,
    set_content_paths,
    add_content_path,
    remove_content_path,
    load_config,
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
    """Tests for load_config()."""

    def test_load_empty_config(self, tmp_config):
        config = load_config()
        assert config == {}

    def test_load_config_with_platforms(self, configured_platforms):
        config = load_config()
        assert "platforms" in config
        assert "devto" in config["platforms"]
