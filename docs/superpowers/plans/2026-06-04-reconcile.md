# reconcile Implementation Plan (Track B, Plan 2)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or executing-plans. Steps use checkbox syntax.

**Goal:** Add a `reconcile` capability (pure matcher + engine + CLI command + MCP tool) that diffs each API platform's live post list against the registry, reports untracked-live and gone-from-platform publications, and (with --apply) backfills/soft-deletes registry rows. Cures the published-but-untracked drift documented in the spec.

**Architecture:** New module `crier/reconcile.py` with a pure `match_live_to_registry` function and a `reconcile_platform` / `reconcile` engine returning structured `ReconcileReport`s. CLI `crier reconcile [--platform] [--apply] [--json]` and MCP `crier_reconcile` are thin wrappers. Engine does registry reads always; registry writes (record_publication / record_deletion) only when `apply=True`.

**Tech stack:** Python 3.10+, existing registry helpers, the Platform ABC `list_articles`.

---

## Background / interfaces (verified)

- `registry.get_platform_publications(platform) -> list[dict]` with keys: `canonical_url`, `title`, `source_file`, `platform_id`, `platform_url`, `published_at`, `rewritten`, `rewrite_author`. This is the registry side.
- `Platform.list_articles(limit) -> list[dict]` with keys: `id`, `title`, `url`, `published`. The live side. (Implemented by every API platform.)
- `registry.record_publication(canonical_url, platform, article_id, url, title=, source_file=, rewritten=, rewrite_author=, posted_content=)` idempotent UPSERT (backfill).
- `registry.record_deletion(canonical_url, platform) -> bool` soft-deletes a publication row.
- `registry.make_slug(title) -> str` for slug-fallback matching.
- `config.get_platform_mode(platform) -> 'api'|'manual'|'import'`; `config.get_api_key`; `platforms.get_platform`; `platforms.PLATFORMS`.
- Scope: API-mode platforms only (manual/import have no live list). Title-drift-vs-content-file repair is OUT of scope (separate concern); this reconciles live-platform vs registry.

## Data shapes

```python
@dataclass
class ReconcileEntry:
    platform: str
    live_id: str | None          # platform_id from the live post
    live_url: str | None
    title: str | None
    canonical_url: str | None    # registry identity when known
    bucket: str                  # "in_both" | "untracked_live" | "gone_from_platform"

@dataclass
class ReconcileReport:
    platform: str
    in_both: list[ReconcileEntry]
    untracked_live: list[ReconcileEntry]      # live but no registry row -> backfill on apply
    gone_from_platform: list[ReconcileEntry]  # registry says published, not in live list -> record_deletion on apply
    applied: bool
    error: str | None = None
```

---

## Task 1: pure matcher + report dataclasses

**Files:** Create `src/crier/reconcile.py`; Test `tests/test_reconcile.py`.

- [ ] Step 1: failing tests for `match_live_to_registry(live_post, registry_rows) -> dict | None`. It returns the matched registry row (dict) or None, tried in order: (1) `live_post["id"] == row["platform_id"]`, (2) `live_post["url"] == row["platform_url"]` (both truthy), (3) `make_slug(live_post["title"]) == make_slug(row["title"])`. Tests: match by id; match by url when id differs/absent; match by slug fallback; no match returns None; id match takes precedence over a conflicting slug.

```python
# tests/test_reconcile.py
from crier.reconcile import match_live_to_registry

def _row(**kw):
    base = {"canonical_url": "https://x/p/", "title": "T", "platform_id": "1", "platform_url": "https://dev/1"}
    base.update(kw); return base

def test_match_by_platform_id():
    rows = [_row(platform_id="abc", canonical_url="https://x/a/")]
    live = {"id": "abc", "url": "https://dev/zzz", "title": "Different"}
    assert match_live_to_registry(live, rows)["canonical_url"] == "https://x/a/"

def test_match_by_url_when_id_differs():
    rows = [_row(platform_id="abc", platform_url="https://dev/9", canonical_url="https://x/b/")]
    live = {"id": "nomatch", "url": "https://dev/9", "title": "Z"}
    assert match_live_to_registry(live, rows)["canonical_url"] == "https://x/b/"

def test_match_by_slug_fallback():
    rows = [_row(platform_id="abc", platform_url="https://dev/1", title="My Post", canonical_url="https://x/c/")]
    live = {"id": "none", "url": "none", "title": "My Post"}
    assert match_live_to_registry(live, rows)["canonical_url"] == "https://x/c/"

def test_no_match_returns_none():
    rows = [_row()]
    assert match_live_to_registry({"id": "z", "url": "z", "title": "Nope"}, rows) is None

def test_id_precedence_over_slug():
    rows = [_row(platform_id="ID1", title="Same Title", canonical_url="https://x/right/"),
            _row(platform_id="ID2", title="Same Title", canonical_url="https://x/wrong/")]
    live = {"id": "ID1", "url": "u", "title": "Same Title"}
    assert match_live_to_registry(live, rows)["canonical_url"] == "https://x/right/"
```

- [ ] Step 2: run -> fail (no module). Step 3: implement `match_live_to_registry` + the dataclasses. Step 4: run -> pass. Step 5: commit `feat(reconcile): pure live-to-registry matcher`.

Implementation sketch:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from .registry import make_slug

def match_live_to_registry(live_post: dict, registry_rows: list[dict]) -> dict | None:
    lid = live_post.get("id")
    if lid:
        for r in registry_rows:
            if r.get("platform_id") and r["platform_id"] == lid:
                return r
    lurl = live_post.get("url")
    if lurl:
        for r in registry_rows:
            if r.get("platform_url") and r["platform_url"] == lurl:
                return r
    ltitle = live_post.get("title")
    if ltitle:
        lslug = make_slug(ltitle)
        for r in registry_rows:
            if r.get("title") and make_slug(r["title"]) == lslug:
                return r
    return None
```

## Task 2: reconcile engine

**Files:** Modify `src/crier/reconcile.py`; Test `tests/test_reconcile.py`.

- [ ] Step 1: failing tests for `reconcile_platform(platform_name, *, apply=False, limit=100)`:
  - Builds live list via `get_platform(name)(api_key).list_articles(limit)` and registry rows via `get_platform_publications(name)`.
  - Classifies: each live post matched -> `in_both`; unmatched live -> `untracked_live`; each registry row whose `platform_id` is not present among live ids/urls -> `gone_from_platform`.
  - With `apply=True`: untracked_live -> `record_publication(canonical_url=None, platform, article_id=live_id, url=live_url, title=live_title)` (creates the article via get_or_create_slug); gone_from_platform -> `record_deletion(canonical_url, platform)`.
  - Non-api platform or missing key -> ReconcileReport with `error` set, empty buckets.
  Mock `crier.reconcile.get_platform`, `crier.reconcile.get_platform_publications`, `crier.reconcile.get_api_key`, `crier.reconcile.get_platform_mode`, and (for apply) `crier.reconcile.record_publication` / `record_deletion`.

- [ ] Step 2: run -> fail. Step 3: implement `reconcile_platform` and `reconcile(platforms=None, *, apply=False, limit=100)` (iterates configured api platforms when `platforms` is None). Step 4: run -> pass. Step 5: commit `feat(reconcile): platform reconcile engine`.

Notes: import the registry/config/platform helpers at module top so tests can patch `crier.reconcile.<name>`. The `gone_from_platform` detection compares registry `platform_id` against the set of live ids, and registry `platform_url` against live urls (a row is "gone" only if neither its id nor url appears live). `apply` backfill uses `record_publication` (idempotent); never delete article rows.

## Task 3: CLI command

**Files:** Modify `src/crier/cli.py`; Test `tests/test_cli.py`.

- [ ] `crier reconcile [PLATFORM...] [--apply] [--json] [--limit N]`. Default dry-run: print a per-platform table of the three buckets with counts. `--apply`: perform writes, print what was applied. `--json`: machine-readable. Follow existing CLI command patterns (Console, json_module, the `@cli.command()` registration). Add tests mirroring existing CLI test style (CliRunner + mocked reconcile engine or mocked platform/registry). Commit `feat(cli): add reconcile command`.

## Task 4: MCP tool

**Files:** Modify `src/crier/mcp_server.py`; Test `tests/test_mcp.py`.

- [ ] Add `crier_reconcile(platform: str | None = None, apply: bool = False, limit: int = 100) -> dict` in the Registry tool category. Lazy-import the engine. Return a dict of per-platform bucket counts + lists (dicts, not dataclasses). Docstring with examples. Add to CLAUDE.md MCP tool count (17 -> 18). Test in test_mcp.py. Commit `feat(mcp): add crier_reconcile tool`.

## Done criteria

- `reconcile.py` pure matcher + engine, fully tested.
- `crier reconcile` and `crier_reconcile` work; dry-run by default, `--apply` writes.
- Full suite green (1259 + new tests), ruff clean.
- No behavior change to existing commands.

## Out of scope

- Title-drift-vs-content-file repair (registry slug frozen while file title changed). Separate concern; reconcile here is live-platform vs registry.
- Reconciling manual/import platforms (no live list).
