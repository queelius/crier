# Platform Plugin System Design

**Date:** 2026-02-13
**Status:** Approved

## Problem

Adding a new platform to Crier requires forking the repo and modifying
`platforms/__init__.py`. Power users who want to add a custom platform
(e.g., Nostr, a private API, a custom webhook) have no extension point.

## Decision

Directory-scan plugin system. User drops a `.py` file in
`~/.config/crier/platforms/`, Crier discovers and loads it automatically.

## Design

### Discovery

- **Location:** `~/.config/crier/platforms/`
- **Mechanism:** `importlib.util.spec_from_file_location()` for each `.py` file
- **Registration:** Scan loaded module for `Platform` subclasses, register by `name` attribute
- **Priority:** User platforms shadow built-ins (user wins on name collision)
- **Error handling:** Per-file try/except; bad plugin warns, doesn't crash

### Loading Rules

1. Skip `__init__.py` and files starting with `_`
2. Load each `.py` file as a module
3. Find all classes that are subclasses of `Platform` (excluding `Platform` itself)
4. Register each by its `name` class attribute
5. If no `name` attribute, use lowercase class name as fallback

### Changes

**`platforms/__init__.py`** (~50 lines):
- New function: `_discover_user_platforms() -> dict[str, type[Platform]]`
- After building built-in `PLATFORMS` dict, call `PLATFORMS.update(_discover_user_platforms())`
- `get_platform()` works unchanged (reads from same dict)

**No changes to:**
- `Platform` ABC interface
- Built-in platform implementations
- Config format
- Registry format
- CLI commands (user platforms appear automatically in `crier platforms`, `crier doctor`)

### Example Plugin

```python
# ~/.config/crier/platforms/nostr.py
from crier.platforms.base import Platform, Article, PublishResult

class Nostr(Platform):
    name = "nostr"
    description = "Publish to Nostr relays"
    max_content_length = None
    supports_delete = False

    def __init__(self, api_key: str):
        super().__init__(api_key)

    def publish(self, article: Article) -> PublishResult:
        ...

    def update(self, article_id, article):
        return PublishResult(success=False, platform=self.name,
                           error="Nostr does not support editing")

    def list_articles(self, limit=10):
        return []

    def get_article(self, article_id):
        return None
```

Usage: `crier config set platforms.nostr.api_key nsec1...`

### Testing

- Valid plugin loads and registers
- Plugin with import error warns but doesn't crash
- Plugin shadows built-in (user version wins)
- Empty/missing directory: no change to PLATFORMS
- Multiple Platform subclasses in one file: all registered

## Alternatives Considered

**Entry points (pip-installable):** Standard Python ecosystem pattern but
adds friction for power users. Can be added later as an additional
discovery mechanism.

**Config-declared import paths:** Explicit but redundant (filename already
implies platform name) and more ceremony than auto-discovery.
