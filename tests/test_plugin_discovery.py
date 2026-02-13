"""Tests for platform discovery (built-in and user plugins)."""

import textwrap
from pathlib import Path

from crier.platforms import (
    _discover_package_platforms,
    _discover_user_platforms,
    get_platform,
    PLATFORMS,
    Platform,
)


def _write_plugin(directory: Path, filename: str, code: str) -> Path:
    """Write a plugin .py file to directory."""
    filepath = directory / filename
    filepath.write_text(textwrap.dedent(code))
    return filepath


class TestDiscoverUserPlatforms:
    """Tests for _discover_user_platforms()."""

    def test_empty_directory(self, tmp_path):
        """Empty plugins dir returns empty dict."""
        result = _discover_user_platforms(tmp_path)
        assert result == {}

    def test_missing_directory(self, tmp_path):
        """Non-existent directory returns empty dict."""
        missing = tmp_path / "does_not_exist"
        result = _discover_user_platforms(missing)
        assert result == {}

    def test_loads_valid_plugin(self, tmp_path):
        """Valid plugin with Platform subclass is discovered."""
        _write_plugin(tmp_path, "custom.py", """\
            from crier.platforms.base import (
                Platform, Article, PublishResult,
            )

            class Custom(Platform):
                name = "custom"
                description = "A custom platform"

                def publish(self, article):
                    pass

                def update(self, article_id, article):
                    pass

                def list_articles(self, limit=10):
                    return []

                def get_article(self, article_id):
                    return None
        """)
        result = _discover_user_platforms(tmp_path)
        assert "custom" in result
        assert issubclass(result["custom"], Platform)
        assert result["custom"].name == "custom"

    def test_skips_underscore_files(self, tmp_path):
        """Files starting with _ are skipped."""
        _write_plugin(tmp_path, "__init__.py", "# nothing")
        _write_plugin(tmp_path, "_helper.py", "x = 1")
        result = _discover_user_platforms(tmp_path)
        assert result == {}

    def test_skips_non_py_files(self, tmp_path):
        """Non-.py files are ignored."""
        (tmp_path / "readme.txt").write_text("not a plugin")
        (tmp_path / "data.json").write_text("{}")
        result = _discover_user_platforms(tmp_path)
        assert result == {}

    def test_bad_plugin_warns_no_crash(self, tmp_path):
        """Plugin with syntax error warns but doesn't crash."""
        _write_plugin(tmp_path, "broken.py", """\
            def this is not valid python
        """)
        # Also add a valid plugin to verify it still loads
        _write_plugin(tmp_path, "good.py", """\
            from crier.platforms.base import (
                Platform, Article, PublishResult,
            )

            class Good(Platform):
                name = "good"
                description = "Works fine"

                def publish(self, article):
                    pass

                def update(self, article_id, article):
                    pass

                def list_articles(self, limit=10):
                    return []

                def get_article(self, article_id):
                    return None
        """)
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = _discover_user_platforms(tmp_path)

        # Good plugin loaded despite broken one
        assert "good" in result
        # Warning was issued for broken plugin
        assert any("broken.py" in str(warning.message) for warning in w)

    def test_multiple_subclasses_in_one_file(self, tmp_path):
        """Multiple Platform subclasses in one file all register."""
        _write_plugin(tmp_path, "multi.py", """\
            from crier.platforms.base import (
                Platform, Article, PublishResult,
            )

            class PlatformA(Platform):
                name = "platform_a"
                description = "First"

                def publish(self, article):
                    pass
                def update(self, article_id, article):
                    pass
                def list_articles(self, limit=10):
                    return []
                def get_article(self, article_id):
                    return None

            class PlatformB(Platform):
                name = "platform_b"
                description = "Second"

                def publish(self, article):
                    pass
                def update(self, article_id, article):
                    pass
                def list_articles(self, limit=10):
                    return []
                def get_article(self, article_id):
                    return None
        """)
        result = _discover_user_platforms(tmp_path)
        assert "platform_a" in result
        assert "platform_b" in result

    def test_no_platform_subclass_skipped(self, tmp_path):
        """File with no Platform subclass is silently skipped."""
        _write_plugin(tmp_path, "utils.py", """\
            def helper():
                return 42
        """)
        result = _discover_user_platforms(tmp_path)
        assert result == {}

    def test_fallback_name_from_class(self, tmp_path):
        """If name attr equals 'base', use lowercase class name."""
        _write_plugin(tmp_path, "webhook.py", """\
            from crier.platforms.base import (
                Platform, Article, PublishResult,
            )

            class Webhook(Platform):
                # name not overridden, still "base"
                description = "Generic webhook"

                def publish(self, article):
                    pass
                def update(self, article_id, article):
                    pass
                def list_articles(self, limit=10):
                    return []
                def get_article(self, article_id):
                    return None
        """)
        result = _discover_user_platforms(tmp_path)
        assert "webhook" in result


class TestPluginShadowsBuiltin:
    """Test that user plugins override built-in platforms."""

    def test_user_platform_shadows_builtin(self, tmp_path):
        """User platform with same name as built-in wins."""
        _write_plugin(tmp_path, "devto.py", """\
            from crier.platforms.base import (
                Platform, Article, PublishResult,
            )

            class CustomDevTo(Platform):
                name = "devto"
                description = "My custom DevTo"

                def publish(self, article):
                    pass
                def update(self, article_id, article):
                    pass
                def list_articles(self, limit=10):
                    return []
                def get_article(self, article_id):
                    return None
        """)
        user_platforms = _discover_user_platforms(tmp_path)
        assert user_platforms["devto"].description == "My custom DevTo"


class TestDiscoverPackagePlatforms:
    """Tests for _discover_package_platforms() built-in discovery."""

    def test_discovers_all_13_builtins(self):
        """All 13 built-in platforms are discovered."""
        result = _discover_package_platforms()
        assert len(result) == 13

    def test_expected_platform_names(self):
        """Discovered platform names match the expected set."""
        result = _discover_package_platforms()
        expected = {
            "devto", "bluesky", "mastodon", "hashnode", "medium",
            "linkedin", "ghost", "buttondown", "telegram", "discord",
            "threads", "wordpress", "twitter",
        }
        assert set(result.keys()) == expected

    def test_all_are_platform_subclasses(self):
        """Every discovered class is a Platform subclass."""
        result = _discover_package_platforms()
        for name, cls in result.items():
            assert issubclass(cls, Platform), f"{name} is not a Platform subclass"

    def test_classes_are_identical_to_direct_imports(self):
        """Discovered classes are the same objects as direct submodule imports."""
        from crier.platforms.devto import DevTo
        from crier.platforms.bluesky import Bluesky
        from crier.platforms.mastodon import Mastodon

        result = _discover_package_platforms()
        assert result["devto"] is DevTo
        assert result["bluesky"] is Bluesky
        assert result["mastodon"] is Mastodon

    def test_name_attributes_match_dict_keys(self):
        """Each class's .name attribute matches its registry key."""
        result = _discover_package_platforms()
        for key, cls in result.items():
            assert cls.name == key, f"{cls.__name__}.name={cls.name!r} != key={key!r}"


class TestBackwardCompatImports:
    """Test that removing hardcoded imports didn't break 'from crier.platforms import X'."""

    def test_import_devto(self):
        """from crier.platforms import DevTo works."""
        from crier.platforms import DevTo
        assert DevTo.name == "devto"

    def test_all_13_class_names_importable(self):
        """All 13 class names are importable from the package."""
        import crier.platforms as pkg
        class_names = [
            "DevTo", "Bluesky", "Mastodon", "Hashnode", "Medium",
            "LinkedIn", "Ghost", "Buttondown", "Telegram", "Discord",
            "Threads", "WordPress", "Twitter",
        ]
        for name in class_names:
            assert hasattr(pkg, name), f"crier.platforms.{name} not found"
            cls = getattr(pkg, name)
            assert issubclass(cls, Platform)

    def test_direct_submodule_import(self):
        """from crier.platforms.devto import DevTo works."""
        from crier.platforms.devto import DevTo
        assert DevTo.name == "devto"

    def test_base_types_importable(self):
        """Base types are still importable from the package."""
        from crier.platforms import (
            Platform, Article, PublishResult,
            DeleteResult, ArticleStats, ThreadPublishResult,
        )
        assert Platform is not None
        assert Article is not None

    def test_platforms_dict_has_all_builtins(self):
        """PLATFORMS dict has at least 13 entries."""
        assert len(PLATFORMS) >= 13

    def test_get_platform_works(self):
        """get_platform() returns the correct class."""
        cls = get_platform("devto")
        assert cls.name == "devto"


class TestPluginIntegration:
    """Test that plugins integrate with the PLATFORMS dict."""

    def test_builtin_platforms_unchanged_without_plugins(self):
        """Without user plugins, PLATFORMS has at least 13 built-ins."""
        # This validates backward compatibility
        assert len(PLATFORMS) >= 13
        assert "devto" in PLATFORMS
        assert "bluesky" in PLATFORMS
        assert "twitter" in PLATFORMS
