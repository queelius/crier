# publish_one Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the api-mode single-post publish state machine into one tested function, `publish_one`, and route the four existing publish call sites through it, so the campaign (Plan 3) and every agent path share one code path.

**Architecture:** New module `crier/publishing.py` exposes `publish_one(file, platform, ...) -> PublishOutcome`. It parses the file, resolves the platform mode and api key, applies an explicit rewrite or runs auto-rewrite, calls `platform.publish()`, and returns the result plus the rewrite bookkeeping. It performs no registry writes, no console output by default, and no prompts, so it is unit-testable and reusable by dry-run and preview. Callers keep ownership of recording and interactive UX. Scope is api mode only; manual, import, and thread handling stay in the interactive `publish` command.

**Tech Stack:** Python 3.10+, Click, pytest, the existing `crier.platforms` ABC, `crier.rewrite` helpers, `crier.registry` UPSERT functions.

---

## Background the implementer needs

Read these before starting:

- `src/crier/platforms/base.py`: `Article` and `PublishResult` dataclasses. `PublishResult(success, platform, article_id=None, url=None, error=None, requires_confirmation=False, manual_content=None, compose_url=None)`.
- `src/crier/rewrite.py`: `apply_rewrite(article, new_body) -> Article` (sets `is_rewrite=True`); `auto_rewrite_for_platform(article, platform_name, max_len, llm_provider, *, retry_count=0, truncate_fallback=False, silent=False, console=None) -> AutoRewriteResult` where `AutoRewriteResult(success, article=None, rewrite_text=None, error=None)`.
- `src/crier/config.py`: `get_platform_mode(platform) -> 'api'|'manual'|'import'`, `get_api_key(platform) -> str|None`.
- `src/crier/converters/markdown.py`: `parse_markdown_file(path) -> Article`.
- `src/crier/platforms/__init__.py`: `get_platform(name) -> type[Platform]`; instantiate with `cls(api_key)`; instance has `.max_content_length` and `.publish(article) -> PublishResult`.
- `src/crier/registry.py`: `record_publication(canonical_url, platform, article_id, url, title=None, source_file=None, rewritten=False, rewrite_author=None, posted_content=None)` and `record_failure(canonical_url, platform, error_msg, title=None, source_file=None)`.

Existing call sites being unified (read them to preserve behavior):

- Interactive `publish` command: `src/crier/cli.py` api branch around lines 995 to 1107 (rewrite/auto-rewrite/publish), recording at 1227 to 1264.
- `audit --publish` main loop: `src/crier/cli.py:3006-3158` (builds `missing_items`, user selects, then per-item auto-rewrite + `plat.publish`/`plat.update` + record). The `update` action path is dead in current crier (actionable items are always `publish`).
- `audit --retry` block: `src/crier/cli.py` lines 2535 to 2608.
- MCP: `src/crier/mcp_server.py` `_prepare_publish` (lines 585 to 633) and `_execute_publish` (636 to 688).

Test conventions (from CLAUDE.md and conftest):

- Platform HTTP is mocked at `crier.platforms.base.requests.<method>` (post/get/put/delete), never per-platform.
- Registry tests set `CRIER_DB` to a temp path, call `reset_connection()` then `init_db()`. Use the `tmp_registry` fixture.
- Set `platform.max_retries = 0` (or on the instance) in tests that mock error responses, to avoid retry loops.
- Run the full suite with `pytest -q`; it is currently 1247 passing.

## Design note discovered during planning

`publish_one` must return more than a `PublishResult`, because when auto-rewrite runs inside it, the caller cannot otherwise know the rewritten text it needs for `posted_content`. So `publish_one` returns a small `PublishOutcome` wrapper carrying the `PublishResult`, the final `Article` actually published, and the rewrite bookkeeping (`rewritten`, `posted_content`, `rewrite_author`). The spec said "returns PublishResult"; this wrapper is a faithful refinement, not a scope change. Dry-run/preview callers can read `outcome.article` without publishing by passing `dry_run=True` (see Task 2).

---

## Task 1: PublishOutcome and the pure prepare step

**Files:**
- Create: `src/crier/publishing.py`
- Test: `tests/test_publishing.py`

- [ ] **Step 1: Write the failing test for prepare_publish (happy path, api mode)**

```python
# tests/test_publishing.py
from unittest.mock import patch

import pytest

from crier.platforms.base import Article
from crier.publishing import PublishOutcome, prepare_publish


def _article():
    return Article(
        title="Hello World",
        body="A" * 50,
        description="desc",
        tags=["python"],
        canonical_url="https://example.com/post/hello/",
    )


@patch("crier.publishing.parse_markdown_file")
@patch("crier.publishing.get_api_key", return_value="real-key")
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_prepare_publish_api_mode_no_rewrite(mode, key, parse):
    parse.return_value = _article()
    plan = prepare_publish("post.md", "devto")
    assert plan.error is None
    assert plan.mode == "api"
    assert plan.api_key == "real-key"
    assert plan.article.title == "Hello World"
    assert plan.rewritten is False
    assert plan.posted_content is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_publishing.py::test_prepare_publish_api_mode_no_rewrite -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'crier.publishing'`.

- [ ] **Step 3: Write the module with PublishOutcome, PublishPlan, and prepare_publish**

```python
# src/crier/publishing.py
"""Single-source publish orchestration.

publish_one() is the one place that turns (file, platform, rewrite options)
into a published result. It performs no registry writes, no console output by
default, and no prompts, so it is unit-testable and reusable by dry-run and
preview. Callers own recording and interactive UX.

Scope: api-mode single-post publishing. Manual, import, and thread handling
stay in the interactive publish command; the backlog campaign does not use
them.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import get_api_key, get_platform_mode
from .converters import parse_markdown_file
from .platforms import get_platform
from .platforms.base import Article, PublishResult
from .rewrite import apply_rewrite, auto_rewrite_for_platform


@dataclass
class PublishPlan:
    """Resolved inputs for a publish, before the platform call.

    error is set (and the other fields may be partial) when the plan cannot
    be built, e.g. wrong mode, missing key, parse failure.
    """

    platform: str
    mode: str
    api_key: str | None
    article: Article | None
    rewritten: bool = False
    posted_content: str | None = None
    rewrite_author: str | None = None
    error: str | None = None


@dataclass
class PublishOutcome:
    """Result of publish_one: the platform result plus rewrite bookkeeping.

    article is the final Article actually sent (post-rewrite). Callers use
    rewritten/posted_content/rewrite_author when recording to the registry.
    """

    result: PublishResult
    article: Article | None
    rewritten: bool = False
    posted_content: str | None = None
    rewrite_author: str | None = None


def prepare_publish(
    file_path: str | Path,
    platform: str,
    *,
    rewrite_content: str | None = None,
    rewrite_author: str | None = None,
    auto_rewrite: bool = False,
    llm_provider=None,
    auto_rewrite_retry: int = 0,
    auto_rewrite_truncate: bool = False,
    draft: bool = False,
    silent: bool = True,
    console=None,
) -> PublishPlan:
    """Parse, resolve mode/key, and apply any rewrite. No network, no I/O.

    Returns a PublishPlan. On any precondition failure the returned plan has
    .error set and .article may be None.
    """
    mode = get_platform_mode(platform)
    if mode != "api":
        return PublishPlan(
            platform=platform, mode=mode, api_key=None, article=None,
            error=f"{platform} is in {mode} mode (not API)",
        )

    api_key = get_api_key(platform)
    if not api_key:
        return PublishPlan(
            platform=platform, mode=mode, api_key=None, article=None,
            error=f"No API key configured for {platform}",
        )

    try:
        article = parse_markdown_file(str(file_path))
    except Exception as e:
        return PublishPlan(
            platform=platform, mode=mode, api_key=api_key, article=None,
            error=f"Failed to parse {file_path}: {e}",
        )

    if not article.title:
        return PublishPlan(
            platform=platform, mode=mode, api_key=api_key, article=None,
            error="Article has no title",
        )

    if draft:
        article.published = False

    rewritten = False
    posted_content = None

    if rewrite_content:
        article = apply_rewrite(article, rewrite_content)
        rewritten = True
        posted_content = rewrite_content
    elif auto_rewrite and llm_provider:
        platform_obj = get_platform(platform)(api_key)
        max_len = platform_obj.max_content_length
        if max_len and len(article.body) > max_len:
            rw = auto_rewrite_for_platform(
                article, platform, max_len, llm_provider,
                retry_count=auto_rewrite_retry,
                truncate_fallback=auto_rewrite_truncate,
                silent=silent, console=console,
            )
            if not rw.success:
                return PublishPlan(
                    platform=platform, mode=mode, api_key=api_key,
                    article=article, error=rw.error,
                )
            article = rw.article
            rewritten = True
            posted_content = rw.rewrite_text
            if not rewrite_author:
                rewrite_author = f"llm:{llm_provider.model}"

    return PublishPlan(
        platform=platform, mode=mode, api_key=api_key, article=article,
        rewritten=rewritten, posted_content=posted_content,
        rewrite_author=rewrite_author,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_publishing.py::test_prepare_publish_api_mode_no_rewrite -v`
Expected: PASS.

- [ ] **Step 5: Add prepare_publish failure-path and rewrite tests**

```python
# tests/test_publishing.py (append)
@patch("crier.publishing.get_platform_mode", return_value="manual")
def test_prepare_publish_rejects_non_api_mode(mode):
    plan = prepare_publish("post.md", "twitter")
    assert plan.error is not None
    assert "manual" in plan.error
    assert plan.article is None


@patch("crier.publishing.get_api_key", return_value=None)
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_prepare_publish_missing_key(mode, key):
    plan = prepare_publish("post.md", "devto")
    assert plan.error is not None
    assert "No API key" in plan.error


@patch("crier.publishing.parse_markdown_file")
@patch("crier.publishing.get_api_key", return_value="real-key")
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_prepare_publish_explicit_rewrite(mode, key, parse):
    parse.return_value = _article()
    plan = prepare_publish("post.md", "bluesky", rewrite_content="short take")
    assert plan.rewritten is True
    assert plan.posted_content == "short take"
    assert plan.article.body == "short take"
    assert plan.article.is_rewrite is True
```

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `pytest tests/test_publishing.py -v`
Expected: 4 passing.

- [ ] **Step 7: Commit**

```bash
git add src/crier/publishing.py tests/test_publishing.py
git commit -m "feat(publishing): add prepare_publish + PublishPlan/PublishOutcome (api mode)"
```

---

## Task 2: publish_one execution

**Files:**
- Modify: `src/crier/publishing.py`
- Test: `tests/test_publishing.py`

- [ ] **Step 1: Write the failing test for publish_one success**

```python
# tests/test_publishing.py (append)
from unittest.mock import MagicMock

from crier.platforms.base import PublishResult
from crier.publishing import publish_one


@patch("crier.publishing.get_platform")
@patch("crier.publishing.parse_markdown_file")
@patch("crier.publishing.get_api_key", return_value="real-key")
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_publish_one_success(mode, key, parse, get_plat):
    parse.return_value = _article()
    inst = MagicMock()
    inst.publish.return_value = PublishResult(
        success=True, platform="devto", article_id="123",
        url="https://dev.to/x/123",
    )
    get_plat.return_value = lambda _key: inst
    outcome = publish_one("post.md", "devto")
    assert outcome.result.success is True
    assert outcome.result.article_id == "123"
    assert outcome.article.title == "Hello World"
    assert outcome.rewritten is False


@patch("crier.publishing.get_platform")
@patch("crier.publishing.parse_markdown_file")
@patch("crier.publishing.get_api_key", return_value="real-key")
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_publish_one_dry_run_does_not_call_publish(mode, key, parse, get_plat):
    parse.return_value = _article()
    inst = MagicMock()
    get_plat.return_value = lambda _key: inst
    outcome = publish_one("post.md", "devto", dry_run=True)
    assert outcome.result.success is True
    assert outcome.article is not None
    inst.publish.assert_not_called()


@patch("crier.publishing.get_platform_mode", return_value="manual")
def test_publish_one_propagates_prepare_error(mode):
    outcome = publish_one("post.md", "twitter")
    assert outcome.result.success is False
    assert "manual" in outcome.result.error
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_publishing.py::test_publish_one_success -v`
Expected: FAIL with `ImportError: cannot import name 'publish_one'`.

- [ ] **Step 3: Implement publish_one**

```python
# src/crier/publishing.py (append)
def publish_one(
    file_path: str | Path,
    platform: str,
    *,
    rewrite_content: str | None = None,
    rewrite_author: str | None = None,
    auto_rewrite: bool = False,
    llm_provider=None,
    auto_rewrite_retry: int = 0,
    auto_rewrite_truncate: bool = False,
    draft: bool = False,
    dry_run: bool = False,
    silent: bool = True,
    console=None,
) -> PublishOutcome:
    """Publish one file to one api-mode platform.

    Does NOT record to the registry, prompt, or (by default) print. Returns a
    PublishOutcome wrapping the PublishResult plus rewrite bookkeeping. On
    dry_run, prepares the article and returns a synthetic success result
    without calling the platform.
    """
    plan = prepare_publish(
        file_path, platform,
        rewrite_content=rewrite_content, rewrite_author=rewrite_author,
        auto_rewrite=auto_rewrite, llm_provider=llm_provider,
        auto_rewrite_retry=auto_rewrite_retry,
        auto_rewrite_truncate=auto_rewrite_truncate,
        draft=draft, silent=silent, console=console,
    )

    if plan.error:
        return PublishOutcome(
            result=PublishResult(success=False, platform=platform, error=plan.error),
            article=plan.article,
        )

    if dry_run:
        return PublishOutcome(
            result=PublishResult(success=True, platform=platform),
            article=plan.article, rewritten=plan.rewritten,
            posted_content=plan.posted_content, rewrite_author=plan.rewrite_author,
        )

    try:
        platform_obj = get_platform(platform)(plan.api_key)
        result = platform_obj.publish(plan.article)
    except Exception as e:
        result = PublishResult(success=False, platform=platform, error=str(e))

    return PublishOutcome(
        result=result, article=plan.article, rewritten=plan.rewritten,
        posted_content=plan.posted_content, rewrite_author=plan.rewrite_author,
    )
```

- [ ] **Step 4: Run the publish_one tests to verify they pass**

Run: `pytest tests/test_publishing.py -v`
Expected: all passing (7 total).

- [ ] **Step 5: Run lint**

Run: `ruff check src/crier/publishing.py tests/test_publishing.py`
Expected: All checks passed.

- [ ] **Step 6: Commit**

```bash
git add src/crier/publishing.py tests/test_publishing.py
git commit -m "feat(publishing): add publish_one execution with dry_run"
```

---

## Task 3: Route MCP publish through publish_one

The MCP server already splits prepare/execute; this swaps its bodies to delegate to `crier.publishing`, keeping the MCP-shaped dict return and the two-step token behavior unchanged.

**Files:**
- Modify: `src/crier/mcp_server.py:636-688` (`_execute_publish`)
- Test: `tests/test_mcp.py` (existing tests must stay green; add one delegation test)

- [ ] **Step 1: Run the existing MCP publish tests to establish the green baseline**

Run: `pytest tests/test_mcp.py -k publish -v`
Expected: all current MCP publish tests pass. Note the count.

- [ ] **Step 2: Replace the body of `_execute_publish` to delegate to publish_one**

Replace lines 636 to 688 (`def _execute_publish(...)` through its `return {...}`) with:

```python
def _execute_publish(
    resolved: Path,
    article,
    platform: str,
    api_key: str,
    is_rewritten: bool,
    posted_content: str | None,
    rewrite_author: str | None,
) -> dict:
    """Run the platform publish call and record the outcome.

    Delegates the publish to crier.publishing.publish_one (the shared
    orchestrator) and records the result here. The article/api_key/rewrite
    inputs were already resolved by _prepare_publish; we pass the file path
    and the explicit rewrite so publish_one re-derives the same Article.
    """
    from .publishing import publish_one
    from .registry import record_failure, record_publication

    canonical = article.canonical_url

    outcome = publish_one(
        str(resolved), platform,
        rewrite_content=posted_content if is_rewritten else None,
        rewrite_author=rewrite_author,
    )
    result = outcome.result

    if not result.success:
        if canonical and result.error:
            record_failure(canonical, platform, result.error, article.title, str(resolved))
        return {"error": f"Publish failed: {result.error}"}

    if canonical:
        record_publication(
            canonical_url=canonical,
            platform=platform,
            article_id=result.article_id,
            url=result.url,
            title=article.title,
            source_file=str(resolved),
            rewritten=is_rewritten,
            rewrite_author=rewrite_author,
            posted_content=posted_content,
        )

    return {
        "success": True,
        "platform": platform,
        "title": article.title,
        "article_id": result.article_id,
        "url": result.url,
    }
```

Note: `_prepare_publish` (585-633) is unchanged; it still validates and builds the preview Article and token. `_execute_publish` now gets the actual publish behavior from `publish_one`, so the api-mode logic lives in one place.

- [ ] **Step 3: Run the MCP publish tests to verify still green**

Run: `pytest tests/test_mcp.py -k publish -v`
Expected: same count as Step 1, all passing.

- [ ] **Step 4: Add a delegation test**

```python
# tests/test_mcp.py (append, near the other publish tests)
def test_execute_publish_delegates_to_publish_one(monkeypatch, tmp_registry):
    """_execute_publish uses publish_one for the platform call."""
    from pathlib import Path
    from unittest.mock import MagicMock

    from crier.platforms.base import Article, PublishResult
    import crier.mcp_server as mcp_server

    called = {}

    def fake_publish_one(file_path, platform, **kwargs):
        called["file_path"] = file_path
        called["platform"] = platform
        from crier.publishing import PublishOutcome
        return PublishOutcome(
            result=PublishResult(success=True, platform=platform,
                                 article_id="99", url="https://x/99"),
            article=Article(title="T", body="b",
                            canonical_url="https://example.com/p/"),
        )

    monkeypatch.setattr("crier.publishing.publish_one", fake_publish_one)

    art = Article(title="T", body="b", canonical_url="https://example.com/p/")
    out = mcp_server._execute_publish(
        Path("p.md"), art, "devto", "key", False, None, None,
    )
    assert out["success"] is True
    assert called["platform"] == "devto"
```

- [ ] **Step 5: Run it**

Run: `pytest tests/test_mcp.py::test_execute_publish_delegates_to_publish_one -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/crier/mcp_server.py tests/test_mcp.py
git commit -m "refactor(mcp): route _execute_publish through publish_one"
```

---

## Task 4: Route the audit --retry block through publish_one

The retry block at cli.py:2535-2608 re-implements parse + publish + record. Swap its publish core for publish_one.

**Files:**
- Modify: `src/crier/cli.py:2514-2608`
- Test: `tests/test_cli.py` (existing audit retry tests must stay green)

- [ ] **Step 1: Establish the green baseline**

Run: `pytest tests/test_cli.py -k "retry or audit" -v`
Expected: current audit/retry tests pass. Note the count.

- [ ] **Step 2: Replace the retry publish core**

Replace lines 2514 to 2608 (the `try: article = parse_markdown_file(...)` through the `except Exception as e:` block that appends to `retry_results`) with the version below. It removes the local parse, api_key resolution, and `platform_inst.publish` in favor of `publish_one`, while keeping the dry-run short-circuit, recording, and `retry_results` shape identical.

```python
                if dry_run:
                    retry_results.append({
                        "platform": platform_name,
                        "canonical_url": canonical_url,
                        "success": True,
                        "action": "would_retry",
                    })
                    continue

                from .publishing import publish_one

                if not silent:
                    console.print(
                        f"[dim]Retrying {platform_name}"
                        f" for {Path(source_file).name}...[/dim]"
                    )

                outcome = publish_one(source_file, platform_name)
                result = outcome.result

                if result.success:
                    record_publication(
                        canonical_url=canonical_url,
                        platform=platform_name,
                        article_id=result.article_id,
                        url=result.url,
                        title=outcome.article.title if outcome.article else None,
                        source_file=source_file,
                    )
                    retry_results.append({
                        "platform": platform_name,
                        "canonical_url": canonical_url,
                        "success": True,
                        "url": result.url,
                    })
                    if not silent:
                        console.print(
                            f"  [green]ok {platform_name}:"
                            f" {result.url or 'published'}[/green]"
                        )
                else:
                    record_failure(
                        canonical_url=canonical_url,
                        platform=platform_name,
                        error_msg=result.error or "Unknown error",
                        title=outcome.article.title if outcome.article else None,
                        source_file=source_file,
                    )
                    retry_results.append({
                        "platform": platform_name,
                        "canonical_url": canonical_url,
                        "success": False,
                        "error": result.error,
                    })
                    if not silent:
                        console.print(
                            f"  [red]x {platform_name}:"
                            f" {result.error}[/red]"
                        )
```

Note: the source-file-exists check at 2505-2512 stays above this block unchanged. publish_one resolves api_key and mode internally, so the old api_key block at 2525-2533 is removed; if a platform is not api mode or has no key, publish_one returns a failure outcome which the `else` branch records, preserving behavior. Keep the surrounding `for` loop, `successes`/`fails` summary, and JSON output (2610+) unchanged.

- [ ] **Step 3: Run the audit/retry tests**

Run: `pytest tests/test_cli.py -k "retry or audit" -v`
Expected: same count as Step 1, all passing. If any test asserted the old "No API key configured" string for a non-api platform, update the assertion to match publish_one's message ("is in manual mode (not API)" or "No API key configured for ...") and note it in the commit.

- [ ] **Step 4: Commit**

```bash
git add src/crier/cli.py tests/test_cli.py
git commit -m "refactor(cli): route audit --retry through publish_one"
```

---

## Task 5: Route the audit --publish main loop through publish_one

The real `audit --publish` publishing loop is at `src/crier/cli.py:3006-3158`. It first builds `missing_items`, lets the user select (or `--yes` selects all), then iterates `selected_items` and, per item, does platform setup, optional auto-rewrite, then `plat.publish` (for the `publish` action) or `plat.update` (for the `update` action), then records. Two facts to preserve:

1. The api-key pre-check (3008-3027) and canonical-url pre-check (3029-3041) produce specific `publish_results` entries ("Not configured", "Missing canonical_url"). Keep them; publish_one re-validates cheaply but those entries and their JSON shape must stay.
2. The `update` action path (`plat.update`) is effectively dead: `actionable_items` is always built with the `"publish"` action (line 2855), because change-detection was removed. Preserve the `update` branch verbatim anyway, so behavior does not change if it ever returns.

**Files:**
- Modify: `src/crier/cli.py:3043-3107` (the `try:` body up to `action_verb = "Updated"`; the result-handling block at 3109-3158 stays unchanged)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Establish the green baseline**

Run: `pytest tests/test_cli.py -k "audit" -v` and note the count.

- [ ] **Step 2: Replace lines 3043-3107 (the try body's dispatch) with a publish_one path plus the preserved update branch**

The block to replace begins at the `try:` on line 3043 and ends at `action_verb = "Updated"` on line 3107. Replace it with:

```python
        try:
            if action == "publish":
                from .publishing import publish_one

                if not silent:
                    console.print(f"[dim]Publishing {title[:30]} → {platform}...[/dim]")
                outcome = publish_one(
                    str(file_path), platform,
                    auto_rewrite=auto_rewrite,
                    llm_provider=llm_provider,
                    auto_rewrite_retry=auto_rewrite_retry or 0,
                    auto_rewrite_truncate=bool(auto_rewrite_truncate),
                    silent=silent,
                    console=console,
                )
                result = outcome.result
                rewritten = outcome.rewritten
                rewrite_content = outcome.posted_content
                action_verb = "Published"
            else:
                # Update path: retained for completeness. Current crier never
                # produces an "update" action here (change-detection was
                # removed, so actionable items are always "publish"), but the
                # branch is preserved so behavior does not change if it returns.
                platform_cls = get_platform(platform)
                plat = platform_cls(api_key)
                publish_article = article
                max_len = platform_cls.max_content_length
                rewritten = False
                rewrite_content = None

                if auto_rewrite and llm_provider and max_len and len(article.body) > max_len:
                    from .rewrite import auto_rewrite_for_platform

                    rw = auto_rewrite_for_platform(
                        article, platform, max_len, llm_provider,
                        retry_count=auto_rewrite_retry or 0,
                        truncate_fallback=bool(auto_rewrite_truncate),
                        silent=silent, console=console,
                    )
                    if rw.success:
                        publish_article = rw.article
                        rewritten = True
                        rewrite_content = rw.rewrite_text
                    else:
                        publish_results.append({
                            "file": str(file_path),
                            "platform": platform,
                            "success": False,
                            "error": rw.error,
                            "action": action,
                        })
                        fail_count += 1
                        continue

                pub_info = get_publication_info(canonical_url, platform)
                if not pub_info or not pub_info.get("article_id"):
                    if not silent:
                        console.print(
                            f"[yellow]⚠ {title[:30]} → {platform}:"
                            f" No article_id in registry,"
                            f" skipping[/yellow]"
                        )
                    publish_results.append({
                        "file": str(file_path),
                        "platform": platform,
                        "success": False,
                        "error": "No article_id in registry",
                        "action": action,
                    })
                    fail_count += 1
                    continue

                article_id = pub_info["article_id"]
                if not silent:
                    console.print(f"[dim]Updating {title[:30]} → {platform}...[/dim]")
                result = plat.update(article_id, publish_article)
                action_verb = "Updated"
```

Leave the result-handling block at 3109-3158 unchanged. It reads `result`, `rewritten`, `rewrite_content`, and calls `get_rewrite_author()` for the author, all of which the publish branch above now sets from `outcome`. Note: the api-mode auto-rewrite for the publish action now happens inside publish_one; an auto-rewrite failure comes back as `result.success is False` with `result.error = rw.error`, and the existing failure branch (3136-3146) appends it to `publish_results` (this loop does not call `record_failure`, matching current behavior).

- [ ] **Step 3: Run the audit tests**

Run: `pytest tests/test_cli.py -k "audit" -v`
Expected: same count as Step 1, all passing. If a test pinned the old auto-rewrite-failure JSON `error` string, it still matches because publish_one passes `rw.error` through unchanged. Reconcile any non-api / missing-key error-string assertions as in Task 4 Step 3.

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: 1247 prior tests plus the new publishing tests, all passing.

- [ ] **Step 5: Commit**

```bash
git add src/crier/cli.py tests/test_cli.py
git commit -m "refactor(cli): route audit --publish loop through publish_one"
```

---

## Task 6: Route the interactive publish command api branch through publish_one (optional, last)

This is the highest-risk site because the api branch is interwoven with manual, import, and thread handling and the interactive confirmation flow. It is NOT required by the backlog campaign (the campaign calls publish_one directly), so it is sequenced last and can be skipped without blocking anything. Including it completes the de-triplication.

**Files:**
- Modify: `src/crier/cli.py` api branch around 995-1107 and recording at 1227-1264
- Test: `tests/test_cli.py`

- [ ] **Step 1: Establish the green baseline**

Run: `pytest tests/test_cli.py -k publish -v` and note the count.

- [ ] **Step 2: Replace only the non-thread api branch**

Inside the per-platform loop, the api branch (the `else` after the manual/import branches, currently lines ~995-1107) contains: a manual-rewrite-too-long check, an auto-rewrite block, a thread block, and the `platform.publish` call. Keep the thread block (`if thread and platform.supports_threads: ...`) exactly as is. For the non-thread path, replace the auto-rewrite + `platform.publish(publish_article)` with:

```python
                else:
                    from .publishing import publish_one

                    if not silent:
                        console.print(f"[dim]Publishing to {platform_name}...[/dim]")
                    outcome = publish_one(
                        file, platform_name,
                        rewrite_content=rewrite_content if rewrite_content else None,
                        rewrite_author=rewrite_author,
                        auto_rewrite=auto_rewrite,
                        llm_provider=llm_provider,
                        auto_rewrite_retry=auto_rewrite_retry or 0,
                        auto_rewrite_truncate=bool(auto_rewrite_truncate),
                        silent=silent,
                        console=console,
                    )
                    result = outcome.result
                    if outcome.rewritten:
                        is_rewritten = True
                        posted_content = outcome.posted_content
                        if not rewrite_author:
                            rewrite_author = outcome.rewrite_author
```

Leave the downstream `if result.requires_confirmation:` block, the normal result handling, and the recording at 1227-1264 unchanged: they operate on `result` and the module-level `is_rewritten`/`posted_content`/`rewrite_author` which the snippet above keeps in sync. The thread branch still produces its own `result` via the existing `type("Result", ...)` conversion.

- [ ] **Step 3: Run the publish command tests**

Run: `pytest tests/test_cli.py -k publish -v`
Expected: same count as Step 1, all passing. Reconcile error-string assertions if needed.

- [ ] **Step 4: Run the full suite and lint**

Run: `pytest -q && ruff check src/ tests/`
Expected: all tests pass, lint clean.

- [ ] **Step 5: Commit**

```bash
git add src/crier/cli.py tests/test_cli.py
git commit -m "refactor(cli): route publish command api branch through publish_one"
```

---

## Done criteria

- `crier/publishing.py` exists with `prepare_publish`, `publish_one`, `PublishPlan`, `PublishOutcome`, fully unit-tested.
- MCP `_execute_publish`, the `audit --retry` block, the `audit --publish` loop, and (optionally) the interactive `publish` api branch all call `publish_one`. The api-mode publish state machine lives in one module.
- Full suite green (1247 prior tests plus the new `test_publishing.py`), ruff clean.
- No behavior change for end users: same results, same recording, same JSON shapes. The only intentional differences are error-message strings for non-api / missing-key cases, which now come from publish_one; update any assertions that pinned the old strings.

## Out of scope (later plans)

- reconcile (Plan 2).
- campaign plan/run (Plan 3), which will call `publish_one` directly.
- Folding manual/import/thread into publish_one. They remain in the interactive command; the backlog campaign does not use them.
