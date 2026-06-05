# Bulk-Publish Hardening (Track B) Design

Status: approved design, pre-implementation
Date: 2026-06-04
Author: Alex Towell (with Claude Code)

## Problem

metafunctor.com has roughly 212 publishable posts. The crier registry shows
only about 24 distinct posts cross-posted anywhere, and only 19 are on all
four API platforms (devto, hashnode, bluesky, mastodon). About 188 posts have
never been cross-posted at all. Fully backfilling the four platforms is on the
order of 760 individual publish operations, roughly 384 of which need a
short-form rewrite (bluesky 300 chars, mastodon 500 chars).

Pushing that backlog through the current code path is slow and risky for three
structural reasons:

1. Publish logic is triplicated. The interactive `publish` command
   (cli.py ~899-1340), the `audit --publish` loop (cli.py ~2540-2600), and the
   MCP `_execute_publish` (mcp_server.py) each re-implement the same state
   machine: load article, resolve api_key, dispatch on platform mode, run
   per-platform rewrite, call publish, record result. The three copies can and
   do drift in behavior.

2. Registry drift is silent and has no cure. Anything published out-of-band
   (web UI, a prior tool, a failed-then-actually-succeeded API call) never
   enters the registry, and there is no command to detect it. This is the
   published-but-untracked bug class hit in a prior session, now multiplied by
   the size of the backlog. About 10 registry entries already fail to match
   their files because titles were edited after first publish (the slug is
   frozen at first publish).

3. The high-quality, agent-authored rewrite path runs through `crier_publish`,
   which is one-file-one-platform with a mandatory two-step confirmation token.
   An agent pushing 30 posts across 4 platforms issues about 240 tool calls and
   120 tokens, with no way to stage rewrites up front or preview the whole run.

## Goals

Make the backlog push:

- Safe: no silent drift (a `reconcile` command detects and repairs it), and the
  registry is the trustworthy source of "what is already done".
- Cheap: rewrites are authored once into a reviewable artifact (the manifest),
  not re-generated on every run; confirmation happens once per campaign, not
  once per cell.
- Resumable: a crashed or partial run resumes by skipping cells already
  recorded as published.
- Maintainable: the publish state machine exists in exactly one place, so new
  platforms and new behaviors are validated on one path, not three.

## Non-goals (deferred to other tracks)

- Splitting the 5220-line cli.py into a commands package (Track C).
- A BrowserPlatform base and new platforms, Nostr, WriteFreely, micro.blog,
  Akkoma (Track D).
- Version-drift cleanup (pyproject 2.0.2 vs newest git tag v0.9.1), stale
  CLAUDE.md and MEMORY counts, the WordPress tag-id and Telegram MarkdownV2
  correctness nits, and the dead-API demotion of Medium and LinkedIn
  (decision D1 below): all deferred to a separate fix-the-rot track. None of
  the four backlog platforms is affected by those, so they do not de-risk this
  push.

## Design Overview

Three components, built in order. Each ships with the full test suite green.

### Component 1: publish_one() orchestrator

New module `crier/publishing.py` with a single function:

```
publish_one(
    file_path: str | Path,
    platform: str,
    *,
    rewrite_content: str | None = None,
    rewrite_author: str | None = None,
    auto_rewrite: bool = False,
    dry_run: bool = False,
    llm_provider=None,
) -> PublishResult
```

Responsibilities (the state machine that is currently copied three times):

1. Parse the markdown file into an `Article` (via existing
   `converters.markdown.parse_markdown_file`).
2. Resolve the api_key and dispatch on `config.get_platform_mode(platform)`,
   which already returns the structured values `'api' | 'manual' | 'import'`.
   No stringly-typed re-detection.
3. Apply a rewrite when appropriate: an explicit `rewrite_content` takes
   precedence and sets `Article.is_rewrite = True` via the existing
   `rewrite.apply_rewrite()` helper; otherwise, if `auto_rewrite` is set and the
   body exceeds the platform `max_content_length`, run
   `rewrite.auto_rewrite_for_platform()`.
4. Call `platform.publish(article)` (or `publish_thread` when threading is
   requested) and return a real `PublishResult`. Manual and import modes return
   a real `PublishResult(requires_confirmation=True, manual_content=...,
   compose_url=...)` rather than the current anonymous `type('Result', ...)`
   fabrication.

What publish_one does NOT do: it does not touch the registry. Recording is the
caller's responsibility, so `dry_run` and campaign previews stay side-effect
free. Callers invoke `registry.record_publication()` or
`registry.record_failure()` on the returned result.

Refactor: the `publish` command, the `audit --publish` loop, and MCP
`_execute_publish` all become thin wrappers over `publish_one`. The bar is
behavior preservation: all 1247 existing tests pass after the refactor.

### Component 2: reconcile

Exposed as `crier reconcile [--platform NAME] [--apply]` and MCP tool
`crier_reconcile`. For each configured API platform it performs a 3-way diff
between live platform state, the registry, and (for title-drift repair) the
content files.

Live side: `platform.list_articles(limit)` returns dicts with `id`, `title`,
`url`, `published`. Registry side: `registry.get_platform_publications(platform)`.

Matching is a pure function, unit-testable with zero network:

```
match_live_to_registry(live_post: dict, registry_rows: list[dict]) -> str | None
```

Tried in order: platform_id equality, then url equality, then
`registry.make_slug(title)` fallback. Returning None means "live post not in
registry".

Three buckets reported:

- live-but-untracked: a live post that matches no registry row. On `--apply`,
  call `registry.record_publication(...)` to backfill it (idempotent UPSERT;
  `get_or_create_slug` creates the article if needed).
- tracked-but-gone: a registry publication with no matching live post. On
  `--apply`, call `registry.record_deletion(...)`.
- in-both: matched. If the registry title differs from the file's current
  title, call `registry.update_article_metadata(...)` to re-sync the
  title-drift cases on `--apply`.

Default is dry-run: print the three buckets and counts, change nothing.
`--apply` performs the writes. reconcile is run first in a campaign so the plan
is built on true state.

### Component 3: campaign manifest

A reviewable YAML artifact plus two lifecycle commands and matching MCP tools.

Format: YAML (decision D4). Rationale: hand-editable, block scalars for
multi-line rewrites, comments allowed, structured (no regex parsing of
structured data). Location (decision D5):
`<site_root>/.crier/campaigns/<name>.yaml`, parallel to the existing
`<site_root>/.crier/schedule.yaml`. Entries are keyed by `canonical_url`
(stable), never by slug (which drifts on title edits).

Schema:

```yaml
campaign: spring-backlog
created: 2026-06-04T00:00:00Z
posts:
  - canonical_url: https://metafunctor.com/post/foo/
    file: content/post/2026-.../index.md
    title: "Foo"
    targets:
      devto:    {status: pending}                # long-form, no rewrite
      hashnode: {status: pending}
      bluesky:  {status: pending, rewrite: ""}    # <=300 chars (agent fills)
      mastodon: {status: pending, rewrite: ""}    # <=500 chars (agent fills)
```

`crier campaign plan [FILTERS] -o NAME` and MCP `crier_campaign_plan` generate
the skeleton: one entry per (post times missing-platform) cell, seeded from
reconcile output plus the content scan, reusing the existing audit filter
pipeline (path, date, tag, profile, sample). Whether a target needs a rewrite
field is derived from `config.is_short_form_platform(platform)`, which reads
the platform class attribute `is_short_form`. No hardcoded short-form list.
Long-form cells carry only `{status: pending}`; short-form cells carry an empty
`rewrite: ""` with the char budget in a trailing comment.

The cross-poster agent fills the `rewrite:` fields by editing the YAML file
directly (it is plain text on disk). A dedicated MCP setter tool
(`crier_campaign_set_rewrite`) is not required for v1; it can be added later if
an agent context lacks file-edit tools. The user then opens the YAML file,
skims and edits once.

`crier campaign run NAME [--apply] [--yes]` and MCP `crier_campaign_run` execute
every `pending` cell through `publish_one`, then write
`status: published | failed`, `url:`, and `error:` back into the manifest, and
record each result in the registry. The run is idempotent and resumable: cells
already `published` are skipped, `failed` cells are retried.

Confirmation happens once at the plan to run boundary (decision D6), not per
cell, which is what removes the ~240-round-trip problem:

- CLI: `crier campaign run NAME` previews the full plan and changes nothing;
  `crier campaign run NAME --apply` executes (with `--yes` to skip the
  interactive confirm prompt, consistent with the existing `audit --publish`
  and `reconcile --apply` conventions).
- MCP `crier_campaign_run`: a single campaign-level confirmation token, reusing
  the existing two-step pattern (call once to get a preview plus token, call
  again with the token to execute) but with ONE token for the entire run rather
  than one per cell.

## Data flow: end-to-end campaign

1. `crier reconcile --apply` trues up the registry against all four platforms,
   backfilling untracked posts and repairing title drift.
2. `crier campaign plan --profile blogs -o spring-backlog` produces
   `.crier/campaigns/spring-backlog.yaml` with every missing cell, short-form
   cells awaiting rewrites.
3. The cross-poster agent fills short-form `rewrite:` fields by editing the
   manifest YAML directly. (MCP `crier_campaign_plan` can also return just the
   cells that still need rewrites, so the agent knows what to fill.)
4. The user reviews and edits the YAML once.
5. `crier campaign run spring-backlog` previews the plan and changes nothing;
   `crier campaign run spring-backlog --apply` executes each cell through
   `publish_one`, recording results and writing status back into the manifest.
6. If the run dies, re-running `crier campaign run spring-backlog` resumes,
   skipping published cells.

## Error handling

- `campaign run` never aborts the batch on a single failure. Each cell outcome
  is written to the manifest and the registry. The command exit code follows
  the existing convention: 0 all succeeded, 1 all failed, 2 partial.
- Manual and import cells (if a non-API platform is in scope) are surfaced as
  `status: needs-manual` with the compose URL in the manifest, never silently
  dropped (the current `--only-api` path hides them).
- reconcile is read-only unless `--apply` is passed.
- publish_one returns structured `PublishResult` with `error` set on failure;
  callers map that to `record_failure(...)`.
- A crashed run is recovered by re-reading the manifest; no separate run-state
  store is needed because the manifest is the run state.

## Testing strategy

- publish_one: unit tests per mode (api, manual, import), rewrite precedence
  (explicit rewrite_content beats auto_rewrite), dry-run side-effect freeness
  (no registry writes), mocked platform requests at
  `crier.platforms.base.requests.*`.
- reconcile matcher: pure-function unit tests for the platform_id, url, and
  slug-fallback paths, plus bucket-classification tests, all with zero network.
- campaign: plan generates the correct skeleton from a fixture content dir plus
  a seeded registry; run executes, records, and writes status back; resume
  skips published cells and retries failed ones; partial-failure exit codes.
- Regression: all 1247 existing tests pass after the three callers are
  refactored onto publish_one. Behavior preservation is the acceptance bar.

## Build sequence

1. publish_one in crier/publishing.py, then refactor the three callers onto it.
   Verify 1247 tests green.
2. reconcile command plus crier_reconcile MCP tool.
3. campaign plan command plus crier_campaign_plan MCP tool.
4. campaign run command plus crier_campaign_run MCP tool.
5. (Optional, only if pulled in from fix-the-rot) dead-API demotion.

Each step is independently shippable with the suite green.

## Decision log

- D1 (dead-API demotion of Medium and LinkedIn): deferred out of Track B to
  the fix-the-rot track. The four backlog platforms are unaffected, so it does
  not de-risk this push. Approved deferred.
- D2 (reconcile matcher): a pure function tried platform_id, then url, then
  slug fallback. Pure so it is testable without network.
- D3 (reconcile default): dry-run by default, `--apply` to write.
- D4 (manifest format): YAML, for hand-editability and structured parsing.
- D5 (manifest location): `<site_root>/.crier/campaigns/<name>.yaml`.
- D6 (confirmation model): once at the plan to run boundary, not per cell.

## Out of scope, explicitly

repo-to-post-stub generation (writing posts for the ~25-30 projects without
posts) is content creation, not distribution, and belongs in a sibling tool
(mf, soul, or repoindex), not in crier. Noted here so it is not silently
absorbed into this work.
