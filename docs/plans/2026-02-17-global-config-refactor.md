# Global Config Refactor

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate local `.crier/config.yaml` — all config lives in `~/.config/crier/config.yaml`. The `.crier/` directory keeps only the registry (publication state).

**Architecture:** One config file (global), one state file (registry at `site_root/.crier/registry.yaml`). Global config gains `site_root` to locate the registry and resolve relative `content_paths`. No merge logic, no precedence rules, no "which file did this come from."

**Tech Stack:** Python 3.12, click, PyYAML

---

## Background

### Current state (broken)

Two config files with implicit precedence:
- **Global** (`~/.config/crier/config.yaml`): API keys, profiles, LLM settings
- **Local** (`.crier/config.yaml`, found by walking up from CWD): `site_base_url`, `content_paths`, `exclude_patterns`, `file_extensions`, `default_profile`, `rewrite_author`, `checks`

`load_config()` merges them — local overrides global for `content_paths` and `profiles`. Every getter function must decide whether to read from `load_config()` (merged) or `load_local_config()` (local only). The `base_path` parameter threads through ~50 call sites.

Running from a different directory (e.g., `~/github/beta/dapple`) means no local config found, so site-specific settings vanish. There's a stashed WIP (`git stash list` in crier) that attempted `site_root` fallback, but it added complexity rather than removing it.

### Target state

```
~/.config/crier/config.yaml    ← ALL config (keys, paths, settings)
<site_root>/.crier/registry.yaml  ← publication state only
```

One config file. No local config. No merge. `site_root` in global config tells crier where the content project and registry live.

Precedence for any value: **global config < env vars < CLI args**. That's it.

### What the global config will look like after

```yaml
# Where the content project lives (for registry + resolving relative content_paths)
site_root: ~/github/repos/metafunctor

# Content discovery
content_paths:
  - content
site_base_url: https://metafunctor.com
exclude_patterns:
  - _index.md
file_extensions:
  - .md

# Defaults
default_profile: everything
rewrite_author: claude-code

# Check severity overrides
checks:
  missing-title: error
  short-body: disabled

# API keys
platforms:
  bluesky:
    api_key: handle:app-password
  devto:
    api_key: ...
  hashnode:
    api_key: ...
  mastodon:
    api_key: instance:token
  medium:
    api_key: import
  twitter:
    api_key: manual

# Publishing profiles
profiles:
  blogs:
    - devto
    - hashnode
    - medium
  social:
    - bluesky
    - mastodon
  everything:
    - blogs
    - social

# LLM config (for auto-rewrite)
llm:
  model: gpt-oss:120b-cloud
  base_url: http://localhost:11434/v1
  api_key: ''
  retry_count: 3
  temperature: 1.2
  truncate_fallback: false
```

### The user's current metafunctor `.crier/config.yaml`

These values move to global config, then this file gets deleted:
```yaml
content_paths: [content]
default_profile: everything
exclude_patterns: [_index.md]
file_extensions: [.md]
rewrite_author: claude-code
site_base_url: https://metafunctor.com
```

The registry (`metafunctor/.crier/registry.yaml`, 22KB, 87 tracked articles) stays.

---

## Task 1: Add `site_root` and migrate config getters to global-only

**Files:**
- Modify: `src/crier/config.py`

### What changes

**Remove entirely:**
- `get_local_config_path()` — no more local config discovery
- `find_local_config()` — no more local config search
- `_find_crier_dir_upward()` — stashed WIP, never merged, but clean it up
- `_get_site_root()` — stashed WIP, replaced by simpler version
- `get_value_source()` — stashed WIP, no longer needed (one source: global)
- `load_local_config()` — no more local config
- `_save_local_config()` — no more local config writes
- `load_config()` merge logic (the part that merges local into global)

**Add:**
- `get_site_root() -> Path | None` — reads `site_root` from global config, expands `~`, returns resolved Path or None

**Simplify `load_config()`:**

Before (merges two files):
```python
def load_config(base_path=None):
    config = {}
    # Load global
    if global_path.exists():
        config = yaml.safe_load(f) or {}
    # Merge local (content_paths, profiles override)
    local_path = get_local_config_path(base_path)
    if local_path.exists():
        local_config = yaml.safe_load(f) or {}
        if "content_paths" in local_config:
            config["content_paths"] = local_config["content_paths"]
        if "profiles" in local_config:
            config["profiles"].update(local_config["profiles"])
    return config
```

After (just reads global):
```python
def load_config():
    """Load configuration from global config file."""
    global_path = get_config_path()
    if global_path.exists():
        with open(global_path) as f:
            return yaml.safe_load(f) or {}
    return {}
```

This is now identical to `load_global_config()`. Keep both for now (callers use both names), alias one to the other. Or just remove `load_global_config()` and have everyone use `load_config()`.

**Migrate every `load_local_config()` caller:**

These functions currently read from local config. Change them to read from `load_config()` (global):

| Function | Key | Current source | New source |
|----------|-----|---------------|------------|
| `get_content_paths()` | `content_paths` | `load_config()` (merged) | `load_config()` (global) |
| `get_site_base_url()` | `site_base_url` | `load_local_config()` | `load_config()` |
| `get_exclude_patterns()` | `exclude_patterns` | `load_local_config()` | `load_config()` |
| `get_file_extensions()` | `file_extensions` | `load_local_config()` | `load_config()` |
| `get_default_profile()` | `default_profile` | `load_local_config()` | `load_config()` |
| `get_rewrite_author()` | `rewrite_author` | `load_local_config()` | `load_config()` |
| `get_check_overrides()` | `checks` | `load_local_config()` | `load_config()` |

Each of these also has a corresponding `set_*()` that calls `_save_local_config()`. Change them to call `save_config()` (global). **Important:** `save_config()` currently dumps the entire config dict. The `set_*` functions should do a read-modify-write on the global config, not overwrite it.

**Drop `base_path` parameter from all getters/setters:**

Every one of these functions takes `base_path: Path | None = None` which was used for local config discovery. Remove this parameter — config is always global now.

This affects ~50 call sites in `cli.py` that pass `base_path=get_project_path()`. All of those become simple calls without arguments.

**`get_project_root()` simplification:**

Before: walk up for `.crier/`, fall back to `site_root`, fall back to CWD.
After: return `get_site_root()` or CWD. No walking.

```python
def get_project_root() -> Path:
    """Get the project root from site_root config, or CWD."""
    return get_site_root() or Path.cwd()
```

### Step 1: Write tests

Add to `tests/test_config.py`:

```python
class TestSiteRoot:
    def test_get_site_root_returns_path(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"site_root": str(tmp_path / "mysite")}))
        monkeypatch.setenv("CRIER_CONFIG", str(config_file))
        (tmp_path / "mysite").mkdir()
        result = get_site_root()
        assert result == (tmp_path / "mysite").resolve()

    def test_get_site_root_expands_tilde(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"site_root": "~/mysite"}))
        monkeypatch.setenv("CRIER_CONFIG", str(config_file))
        result = get_site_root()
        assert result == Path.home().resolve() / "mysite"

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
```

```python
class TestGlobalOnlyConfig:
    """Config is global-only — no local config, no merge logic."""

    def test_load_config_reads_global(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "content_paths": ["content"],
            "site_base_url": "https://example.com",
        }))
        monkeypatch.setenv("CRIER_CONFIG", str(config_file))
        cfg = load_config()
        assert cfg["content_paths"] == ["content"]
        assert cfg["site_base_url"] == "https://example.com"

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
```

### Step 2: Implement changes in config.py

1. Add `get_site_root()`.
2. Simplify `load_config()` — remove merge logic, remove `base_path` param.
3. Remove `load_local_config()`, `_save_local_config()`, `get_local_config_path()`, `find_local_config()`.
4. Keep `load_global_config()` as an alias for `load_config()` (or remove and update callers).
5. Change all getters (`get_site_base_url`, `get_exclude_patterns`, etc.) to call `load_config()` instead of `load_local_config()`. Remove `base_path` param from each.
6. Change all setters (`set_site_base_url`, `set_exclude_patterns`, etc.) to do read-modify-write on global config. Remove `base_path` param.
7. Simplify `get_project_root()`.
8. Fix `save_config()` — it currently dumps entire dict. Make sure setters do read-modify-write correctly.

### Step 3: Run tests

```bash
pytest tests/test_config.py -v
```

Many existing tests will break because they test local config behavior. Fix or remove them:
- `TestLoadLocalConfig` — delete entirely
- `TestConfigPaths` — rewrite for global-only behavior
- `TestLoadConfig` — simplify (no merge to test)
- `TestLoadConfigWithBasePath` — delete or rewrite
- Tests that use `tmp_config` fixture creating `.crier/config.yaml` — rewrite to use global config via `CRIER_CONFIG` env var

### Step 4: Commit

```
Simplify config: global-only, no local config merge
```

---

## Task 2: Update registry to use `site_root`

**Files:**
- Modify: `src/crier/registry.py`

### What changes

`get_registry_path()` currently walks up from CWD looking for `.crier/`. Change it to use `site_root`:

```python
def get_registry_path() -> Path:
    """Get the path to the registry file.

    Located at <site_root>/.crier/registry.yaml.
    Falls back to CWD/.crier/ if site_root not configured.
    """
    from .config import get_site_root
    root = get_site_root() or Path.cwd()
    return root / REGISTRY_DIR / REGISTRY_FILE
```

Remove `base_path` parameter — registry location is determined by `site_root`, not by a caller-provided path.

### Step 1: Write test

```python
def test_registry_path_uses_site_root(tmp_path, monkeypatch):
    site = tmp_path / "mysite"
    (site / ".crier").mkdir(parents=True)
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"site_root": str(site)}))
    monkeypatch.setenv("CRIER_CONFIG", str(config_file))
    monkeypatch.chdir(tmp_path / "elsewhere")  # CWD is not the site
    (tmp_path / "elsewhere").mkdir()
    assert get_registry_path() == site / ".crier" / "registry.yaml"
```

### Step 2: Implement

Simplify `get_registry_path()` as shown above. Remove `base_path` param.

### Step 3: Fix callers

Every call to `get_registry_path(base_path=get_project_path())` in `cli.py` and internal functions becomes just `get_registry_path()`. There are ~30 such call sites in `registry.py` functions that accept and forward `base_path`.

Grep for `base_path` in `registry.py` — every public function there takes it. Remove the parameter from all of them:
- `record_publication()`
- `record_thread_publication()`
- `record_failure()`
- `get_failures()`
- `is_published()`
- `has_content_changed()`
- `get_publication_info()`
- `get_platform_publications()`
- `get_article_by_file()`
- `get_all_articles()`
- `remove_publication()`
- `record_deletion()`
- `is_archived()`, `set_archived()`
- `get_cached_stats()`, `get_stats_age_seconds()`

### Step 4: Run tests

```bash
pytest tests/test_registry.py -v
```

Fix broken tests — they use `base_path` to isolate to tmp dirs. Rewrite to use `CRIER_CONFIG` env var pointing to a tmp global config with `site_root`.

### Step 5: Commit

```
Simplify registry: use site_root instead of CWD walk
```

---

## Task 3: Update `utils.py` — content path resolution

**Files:**
- Modify: `src/crier/utils.py`

### What changes

`find_content_files()` and `is_in_content_paths()` resolve relative content paths. They currently resolve against CWD. Change to resolve against `get_project_root()`.

```python
def find_content_files(explicit_path=None):
    ...
    if not explicit_path:
        from .config import get_project_root
        project_root = get_project_root()
        for content_path in content_paths:
            path_obj = Path(content_path)
            if not path_obj.is_absolute():
                path_obj = project_root / path_obj
            ...
```

Same pattern for `is_in_content_paths()`.

### Step 1: Write test

```python
def test_find_content_files_resolves_against_site_root(tmp_path, monkeypatch):
    site = tmp_path / "mysite"
    content = site / "content" / "post" / "hello"
    content.mkdir(parents=True)
    (content / "index.md").write_text("---\ntitle: Hello\n---\nHi")
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({
        "site_root": str(site),
        "content_paths": ["content"],
        "file_extensions": [".md"],
    }))
    monkeypatch.setenv("CRIER_CONFIG", str(config_file))
    monkeypatch.chdir(tmp_path)  # CWD is NOT the site
    files = find_content_files()
    assert len(files) == 1
    assert files[0].name == "index.md"
```

### Step 2: Implement and test

```bash
pytest tests/test_utils.py -v
```

### Step 3: Commit

```
Resolve content paths against site_root
```

---

## Task 4: Update CLI — remove `base_path` threading

**Files:**
- Modify: `src/crier/cli.py`

### What changes

**Remove `--project` flag and `get_project_path()`.**

The `--project` flag was the manual override for local config discovery. With global-only config, it's not needed — `site_root` in global config serves the same purpose. If someone wants a different site root temporarily, they can set `CRIER_CONFIG` to a different global config file.

Remove:
- `get_project_path()` function
- `--project` option from `cli()` group
- `ctx.obj["project_path"]` setup

**Remove all `base_path=get_project_path()` arguments.**

There are ~60 call sites in `cli.py` passing `base_path=get_project_path()`. Every one becomes a simple call without arguments:

```python
# Before
content_paths = get_content_paths(base_path=get_project_path())
registry_path = get_registry_path(base_path=get_project_path())
site_base_url = get_site_base_url(base_path=get_project_path())

# After
content_paths = get_content_paths()
registry_path = get_registry_path()
site_base_url = get_site_base_url()
```

**Simplify `config show`.**

No need for source annotations per value — there's only one source (global config). Show:

```
Configuration
  Config file: ~/.config/crier/config.yaml
  Site root:   ~/github/repos/metafunctor
  Registry:    ~/github/repos/metafunctor/.crier/registry.yaml

  content_paths:    content                    ✓
  site_base_url:    https://metafunctor.com
  exclude_patterns: _index.md
  file_extensions:  .md
  default_profile:  everything
  rewrite_author:   claude-code

  [platforms table]
  [profiles table]
```

**Simplify `init` command.**

Currently creates `.crier/config.yaml`. Change to:
1. Create `.crier/` directory (for registry)
2. Create empty registry file
3. Detect content directories and write to global config
4. Prompt for API keys and write to global config
5. Set `site_root` in global config to CWD

### Step 1: Implement

This is mostly mechanical — search and replace `base_path=get_project_path()` with nothing.

### Step 2: Run full test suite

```bash
pytest -v
```

### Step 3: Commit

```
Remove --project flag and base_path threading from CLI
```

---

## Task 5: Update tests

**Files:**
- Modify: `tests/test_config.py` (137 tests — many will need rewriting)
- Modify: `tests/test_registry.py` (87 tests — update base_path usage)
- Modify: any other test files that use local config fixtures

### What changes

**Test isolation strategy:**

Currently tests create `.crier/config.yaml` in tmp directories. New strategy: set `CRIER_CONFIG` env var to a tmp file via monkeypatch.

Common fixture:
```python
@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Provide an isolated global config for testing."""
    config_file = tmp_path / "crier_config.yaml"
    config_file.write_text(yaml.dump({}))
    monkeypatch.setenv("CRIER_CONFIG", str(config_file))
    return config_file
```

For registry tests, also set `site_root`:
```python
@pytest.fixture
def tmp_site(tmp_path, monkeypatch):
    """Provide an isolated site with global config and registry."""
    site = tmp_path / "site"
    (site / ".crier").mkdir(parents=True)
    config_file = tmp_path / "crier_config.yaml"
    config_file.write_text(yaml.dump({"site_root": str(site)}))
    monkeypatch.setenv("CRIER_CONFIG", str(config_file))
    return site
```

**Delete test classes:**
- `TestLoadLocalConfig` — no local config
- `TestConfigPaths` (the CWD-walk tests) — no more walking

**Rewrite test classes:**
- `TestLoadConfig` — simplify, no merge semantics
- `TestLoadConfigWithBasePath` — remove (no base_path)
- All setter tests — verify they write to global config

### Step 1: Implement test changes

### Step 2: Run full suite

```bash
pytest --cov=crier --cov-report=term-missing
```

### Step 3: Commit

```
Update tests for global-only config
```

---

## Task 6: Migrate user config and clean up

**Files:**
- Modify: `~/.config/crier/config.yaml` — absorb local config values, add `site_root`
- Delete: `~/github/repos/metafunctor/.crier/config.yaml` (keep `registry.yaml`)

### Step 1: Merge local config into global

The global config should become:

```yaml
site_root: ~/github/repos/metafunctor
content_paths:
  - content
site_base_url: https://metafunctor.com
exclude_patterns:
  - _index.md
file_extensions:
  - .md
default_profile: everything
rewrite_author: claude-code
platforms:
  bluesky:
    api_key: <existing>
  devto:
    api_key: <existing>
  hashnode:
    api_key: <existing>
  mastodon:
    api_key: <existing>
  medium:
    api_key: import
  twitter:
    api_key: manual
profiles:
  blogs: [devto, hashnode, medium]
  social: [bluesky, mastodon]
  everything: [blogs, social]
llm:
  <existing>
```

### Step 2: Delete local config file

```bash
rm ~/github/repos/metafunctor/.crier/config.yaml
```

Keep `~/github/repos/metafunctor/.crier/registry.yaml` — that's publication state.

### Step 3: Verify

```bash
# From any directory
crier config show
crier audit
crier doctor
```

### Step 4: Drop the stash

```bash
cd ~/github/repos/crier
git stash drop  # the WIP site_root attempt
```

---

## Task 7: Update docs, skill, and CLAUDE.md

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md` (if exists)
- Modify: `~/.claude/skills/crier/crier.md` (the Claude Code skill file)

### What changes

- Document global-only config model
- Document `site_root` key
- Update `crier init` docs
- Remove references to `.crier/config.yaml`
- Update `crier config show` description

### Step 1: Implement

### Step 2: Commit

```
Update docs for global-only config model
```

---

## Summary of deletions

| Removed | Reason |
|---------|--------|
| `load_local_config()` | No local config |
| `_save_local_config()` | No local config |
| `get_local_config_path()` | No local config |
| `find_local_config()` | No local config |
| `get_value_source()` | Only one source now |
| `--project` CLI flag | `site_root` replaces it |
| `get_project_path()` | `site_root` replaces it |
| `base_path` param on ~20 functions | Not needed with global config |
| `base_path=get_project_path()` on ~60 call sites | Not needed |
| `metafunctor/.crier/config.yaml` | Config moved to global |

## What stays

| Kept | Reason |
|------|--------|
| `~/.config/crier/config.yaml` | The one config file |
| `<site_root>/.crier/registry.yaml` | Publication state is per-project |
| `CRIER_CONFIG` env var | Override global config path |
| `CRIER_*_API_KEY` env vars | Override API keys |
| `get_registry_path()` | Still needed, now uses `site_root` |
| `crier init` | Still needed, now writes to global config |
