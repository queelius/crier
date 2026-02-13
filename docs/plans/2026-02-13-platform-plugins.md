# Platform Plugin System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow users to add custom platforms by dropping `.py` files in `~/.config/crier/platforms/`.

**Architecture:** Add a `_discover_user_platforms()` function to `platforms/__init__.py` that scans a well-known directory for `.py` files, dynamically imports them, finds `Platform` subclasses, and merges them into the `PLATFORMS` dict (user platforms shadow built-ins). All existing behavior is unchanged when no user plugins exist.

**Tech Stack:** `importlib.util` (stdlib), `inspect` (stdlib). No new dependencies.

---

### Task 1: Write tests for plugin discovery

**Files:**
- Create: `tests/test_plugin_discovery.py`

**Step 1: Write the test file**

All tests use a temp directory as the plugins dir, patching the discovery
path. Create a conftest-style helper that writes `.py` files to temp dirs.

```python
"""Tests for user platform plugin discovery."""

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from crier.platforms import (
    _discover_user_platforms,
    PLATFORMS,
    Platform,
)
from crier.platforms.base import Article, PublishResult


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


class TestPluginIntegration:
    """Test that plugins integrate with the PLATFORMS dict."""

    def test_builtin_platforms_unchanged_without_plugins(self):
        """Without user plugins, PLATFORMS has exactly 13 built-ins."""
        # This validates backward compatibility
        assert len(PLATFORMS) >= 13
        assert "devto" in PLATFORMS
        assert "bluesky" in PLATFORMS
        assert "twitter" in PLATFORMS
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugin_discovery.py -v`
Expected: FAIL — `_discover_user_platforms` not importable

**Step 3: Commit the failing tests**

```bash
git add tests/test_plugin_discovery.py
git commit -m "test: add plugin discovery tests (red)"
```

---

### Task 2: Implement plugin discovery

**Files:**
- Modify: `src/crier/platforms/__init__.py`

**Step 1: Add `_discover_user_platforms()` function**

Add this between the `PLATFORMS` dict definition and `get_platform()`:

```python
import importlib.util
import inspect
import sys
import warnings
from pathlib import Path


# Default user plugins directory
USER_PLATFORMS_DIR = Path.home() / ".config" / "crier" / "platforms"


def _discover_user_platforms(
    plugins_dir: Path | None = None,
) -> dict[str, type[Platform]]:
    """Discover user-defined Platform subclasses from .py files.

    Args:
        plugins_dir: Directory to scan. Defaults to
            ~/.config/crier/platforms/

    Returns:
        Dict mapping platform name to Platform subclass.
    """
    if plugins_dir is None:
        plugins_dir = USER_PLATFORMS_DIR

    if not plugins_dir.is_dir():
        return {}

    discovered: dict[str, type[Platform]] = {}

    for filepath in sorted(plugins_dir.glob("*.py")):
        if filepath.name.startswith("_"):
            continue

        module_name = f"crier_plugin_{filepath.stem}"
        try:
            spec = importlib.util.spec_from_file_location(
                module_name, filepath,
            )
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception as exc:
            warnings.warn(
                f"Failed to load platform plugin {filepath.name}: {exc}",
                stacklevel=1,
            )
            continue

        # Find all Platform subclasses in the module
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, Platform)
                and obj is not Platform
                and obj.__module__ == module_name
            ):
                platform_name = obj.name
                if platform_name == "base":
                    platform_name = obj.__name__.lower()
                discovered[platform_name] = obj

    return discovered
```

**Step 2: Merge user platforms into PLATFORMS dict**

After the `PLATFORMS = { ... }` dict, add:

```python
# Load user-defined platforms (override built-ins)
PLATFORMS.update(_discover_user_platforms())
```

**Step 3: Export the function**

Add `"_discover_user_platforms"` and `"USER_PLATFORMS_DIR"` to `__all__`.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_plugin_discovery.py -v`
Expected: ALL PASS

**Step 5: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All 978+ tests pass (no regressions)

**Step 6: Run lint**

Run: `ruff check src/crier/platforms/__init__.py`
Expected: All checks passed

**Step 7: Commit**

```bash
git add src/crier/platforms/__init__.py
git commit -m "feat: add user platform plugin discovery"
```

---

### Task 3: Update documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`

**Step 1: Add plugin section to CLAUDE.md**

In the "Adding a New Platform" section, add a "User Plugins" subsection explaining:
- Drop `.py` file in `~/.config/crier/platforms/`
- Must subclass `Platform` from `crier.platforms.base`
- Set `name` class attribute
- Implement 4 abstract methods: `publish`, `update`, `list_articles`, `get_article`
- Configure API key: `crier config set platforms.<name>.api_key <key>`

**Step 2: Add plugin section to README.md**

Add a "Custom Platforms" section with the nostr example from the design doc.

**Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: add user platform plugin documentation"
```
