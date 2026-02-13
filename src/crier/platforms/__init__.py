"""Platform implementations for crier.

Built-in platforms are auto-discovered from .py files in this package.
User plugins are loaded from ~/.config/crier/platforms/.
"""

import importlib
import importlib.util
import inspect
import sys
import warnings
from pathlib import Path

from .base import Platform, Article, PublishResult, DeleteResult, ArticleStats, ThreadPublishResult

# Modules to skip during built-in discovery
_SKIP_MODULES = frozenset({"__init__", "base"})

# Default user plugins directory
USER_PLATFORMS_DIR = Path.home() / ".config" / "crier" / "platforms"


def _discover_package_platforms() -> dict[str, type[Platform]]:
    """Discover built-in Platform subclasses from .py files in this package.

    Scans the package directory for Python modules, imports each one via
    importlib.import_module (preserving package context for relative imports),
    and collects all Platform subclasses.

    Returns:
        Dict mapping platform name to Platform subclass.
    """
    pkg_dir = Path(__file__).parent
    discovered: dict[str, type[Platform]] = {}

    for filepath in sorted(pkg_dir.glob("*.py")):
        stem = filepath.stem
        if stem.startswith("_") or stem in _SKIP_MODULES:
            continue
        try:
            module = importlib.import_module(f".{stem}", __package__)
        except Exception as exc:
            warnings.warn(
                f"Failed to load built-in platform {stem}: {exc}",
                stacklevel=1,
            )
            continue

        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, Platform)
                and obj is not Platform
                and obj.__module__ == f"crier.platforms.{stem}"
            ):
                platform_name = obj.name if obj.name != "base" else obj.__name__.lower()
                discovered[platform_name] = obj

    return discovered


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


# Build unified PLATFORMS registry: built-ins first, user plugins override
_builtin_platforms = _discover_package_platforms()
PLATFORMS: dict[str, type[Platform]] = dict(_builtin_platforms)
PLATFORMS.update(_discover_user_platforms())

# Backward compat: inject class names into package namespace so
# "from crier.platforms import DevTo" etc. still work
for _cls in _builtin_platforms.values():
    globals()[_cls.__name__] = _cls
for _cls in PLATFORMS.values():
    globals()[_cls.__name__] = _cls


def get_platform(name: str) -> type[Platform]:
    """Get a platform class by name."""
    if name not in PLATFORMS:
        from difflib import get_close_matches

        # Suggest closest match
        suggestions = get_close_matches(name, PLATFORMS.keys(), n=1, cutoff=0.6)
        available = ", ".join(sorted(PLATFORMS.keys()))

        error_msg = f"Unknown platform: {name}"
        if suggestions:
            error_msg += f"\nDid you mean: {suggestions[0]}?"
        error_msg += f"\n\nAvailable platforms: {available}"
        raise ValueError(error_msg)
    return PLATFORMS[name]


# Dynamic __all__ — base types + utilities + discovered class names
__all__ = [
    "Platform",
    "Article",
    "PublishResult",
    "DeleteResult",
    "ArticleStats",
    "ThreadPublishResult",
    "PLATFORMS",
    "get_platform",
    "_discover_package_platforms",
    "_discover_user_platforms",
    "USER_PLATFORMS_DIR",
    *[cls.__name__ for cls in PLATFORMS.values()],
]
