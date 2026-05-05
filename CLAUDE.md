# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Crier is a CLI tool for cross-posting content to multiple platforms. It reads markdown files with YAML or TOML front matter and publishes them via platform APIs. Designed to be used with Claude Code for automated content distribution.

## Development Commands

```bash
# Install in development mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=crier

# Run a single test
pytest tests/test_file.py::test_function -v

# Lint
ruff check src/

# Format check
ruff format --check src/
```

## Architecture

**CLI Layer** (`cli.py`): Click-based commands that orchestrate the workflow:
- `init` — Interactive setup wizard
- `publish` — Publish to platforms (supports `--dry-run`, `--profile`, `--manual`, `--rewrite`, `--auto-rewrite`, `--batch`, `--json`, `--schedule`, `--thread`, `--no-check`, `--strict`)
- `check` — Pre-publish content validation (supports `--to`, `--all`, `--json`, `--strict`, `--check-links`)
- `status` — Show publication status for files
- `audit` — Check what's missing (supports bulk operations with filters, `--batch`, `--json`, `--include-archived`, `--check`, `--failed`, `--retry`)
- `search` — Search and list content with metadata (supports `--tag`, `--since`, `--until`, `--sample`, `--json`)
- `delete` — Delete content from platforms (`--from`, `--all`, `--dry-run`)
- `archive` / `unarchive` — Exclude/include content from audit --publish
- `schedule` — Manage scheduled posts (`list`, `show`, `cancel`, `run`)
- `stats` — View engagement statistics (`--refresh`, `--top`, `--since`, `--json`, `--compare`, `--export`)
- `feed` — Generate RSS/Atom feeds from content files (`--format`, `--output`, `--limit`, `--tag`)
- `doctor` — Validate API keys (`--json`)
- `config` — Manage API keys, profiles, and content paths (`set`, `get`, `show`, `profile`, `path`, `llm`)
- `skill` — Manage Claude Code skill installation (deprecated -- use crier plugin from queelius-plugins marketplace)
- `register` / `unregister` — Manual registry management
- `list` — List articles on a platform (default: registry; `--remote` for live API)
- `mcp` — Start MCP server for Claude Code integration (`--http` for SSE mode)

**LLM Module** (`llm/`): Optional auto-rewrite using OpenAI-compatible APIs:
- `provider.py`: Abstract `LLMProvider` interface and `RewriteResult` dataclass
- `openai_compat.py`: `OpenAICompatProvider` for OpenAI, Ollama, Groq, etc.

**Platform Abstraction** (`platforms/`):
- `base.py`: Abstract `Platform` class defining the interface (`publish`, `update`, `list_articles`, `get_article`, `delete`, `get_stats`, `publish_thread`) and core data classes (`Article`, `PublishResult`, `DeleteResult`, `ArticleStats`, `ThreadPublishResult`)
- `base.py` also provides `retry_request()` — centralized HTTP retry with exponential backoff, Retry-After header parsing, and retryable/non-retryable status code classification
- Platform capabilities: `supports_delete`, `supports_stats`, `supports_threads`, `thread_max_posts`
- Each platform implements the `Platform` interface; all use `self.retry_request()` instead of direct `requests.*()` calls
- `_discover_package_platforms()` in `__init__.py` auto-discovers built-in platforms by scanning `.py` files in the package (no hardcoded imports)
- `_discover_user_platforms()` loads user plugins from `~/.config/crier/platforms/`; user plugins override built-ins
- `PLATFORMS` registry in `__init__.py` maps platform names to classes (built-in + user plugins)
- Backward compat: `globals()` injection ensures `from crier.platforms import DevTo` etc. still work

**Scheduler** (`scheduler.py`): Content scheduling for future publication:
- `ScheduledPost` dataclass for scheduled post data
- Schedule storage in `<site_root>/.crier/schedule.yaml`
- Natural language time parsing via `dateparser`

**Checker** (`checker.py`): Pre-publish content validation:
- `CheckResult` and `CheckReport` dataclasses for validation findings
- `check_article()` — Pure validation (no I/O): front matter, content, platform-specific checks
- `check_file()` — I/O wrapper that reads file and calls `check_article()`
- `check_external_links()` — Optional external URL validation via HEAD requests
- Configurable severity overrides in `~/.config/crier/config.yaml` `checks:` section
- Integrated into `publish` (pre-publish gate) and `audit` (filter with `--check`)

**Threading** (`threading.py`): Thread splitting for social platforms:
- `split_into_thread()` splits content by manual markers, paragraphs, or sentences
- `format_thread()` adds thread indicators (numbered, emoji, or simple style)
- Used by Bluesky and Mastodon `publish_thread()` implementations

**Platform Categories** (14 total):
- Blog: devto, hashnode, medium, ghost, wordpress
- Newsletter: buttondown
- Social: bluesky, mastodon, pleroma, linkedin, threads, twitter (copy-paste mode)
- Announcement: telegram, discord

Mastodon and Pleroma both inherit from `FediversePlatform` (defined in `platforms/_fediverse.py`) which encapsulates the Mastodon-API-compatible REST protocol. The leading underscore on the module name keeps the base class out of platform auto-discovery; only its concrete subclasses (each with their own `name`, `default_instance`, and `max_content_length`) get registered. Adding Akkoma, GoToSocial, or another Mastodon-API-compatible server is a ~10-line subclass.

**Config** (`config.py`): Single global configuration:
- **Global** (`~/.config/crier/config.yaml`): ALL configuration -- API keys, profiles, content paths, site settings
- `site_root` key locates the content project directory (e.g., `~/github/repos/my-blog`)
- No local `.crier/config.yaml` -- no merge logic
- Precedence: global config < environment variables (`CRIER_{PLATFORM}_API_KEY`, `CRIER_DB`) < CLI args
- Supports composable profiles (profiles can reference other profiles)

Example global config structure:
```yaml
site_root: ~/github/repos/my-blog
site_base_url: https://example.com
content_paths:
  - content/post
  - content/note
file_extensions:
  - .md
  - .markdown
exclude_patterns:
  - _drafts/*
  - _index.md
default_profile: blogs

platforms:
  devto:
    api_key: sk-...
  bluesky:
    handle: user.bsky.social
    app_password: ...

profiles:
  blogs:
    platforms: [devto, hashnode, medium]
  social:
    platforms: [bluesky, mastodon]

checks:
  missing-tags: disabled
  missing-date: error

llm:
  api_key: sk-...
  model: gpt-4o-mini
```

**Feed** (`feed.py`): RSS/Atom feed generation from content files:
- `generate_feed()` — Builds RSS 2.0 or Atom XML from markdown files using `feedgen`
- `_collect_items()` — Parses files and applies tag/date filters
- Reuses `parse_markdown_file()`, `get_content_date()`, `get_content_tags()`

**Registry** (`registry.py`): SQLite database at `~/.config/crier/crier.db` (global, single file for all projects).
- **Slug primary key** derived from title via `python-slugify` (not canonical_url). Slug is stable; if the title changes, the slug stays.
- `canonical_url` is optional metadata, not the identity. A unique index allows lookup but it can be `NULL`.
- **No content hashes**. Change detection was removed entirely. If content is outdated, re-publish manually.
- **`_resolve_slug(conn, key)`** is the dispatcher for the dual-key API: every public function accepts either a slug or a canonical_url. It tries the cheap primary-key lookup first, then the canonical_url unique index.
- `get_or_create_slug(title, canonical_url, source_file)` finds or creates an article entry. Used everywhere a publication is recorded.
- `update_article_metadata(slug, title, source_file, canonical_url, section)` is the public wrapper for editing article metadata. CLI's `link` command uses this; do NOT import the private `_update_article_metadata` from outside `registry.py`.
- `record_failure()` / `get_failures()`: failure rows have `platform_id IS NULL`. Most queries filter `WHERE platform_id IS NOT NULL AND deleted_at IS NULL` to get "real" publications; remember this when writing new SQL against the registry.
- **UPSERT on `record_publication` / `record_thread_publication` / `save_stats` / `record_failure`.** UPSERT (not `INSERT OR REPLACE`) is required because `INSERT OR REPLACE` deletes and reinserts the row, which cascade-deletes dependent stats and silently resets unspecified columns. The UPSERT clauses explicitly enumerate `deleted_at = NULL`, `last_error = NULL`, `is_thread`, `thread_ids`, `posted_content` so re-publishing a soft-deleted post resurrects it cleanly. See regression tests in `TestDeletionPreservesHistory`.
- `CRIER_DB` env var overrides DB path (used for test isolation).
- Module-level `_connection` cache; `reset_connection()` is required between tests with different DBs.
- SQLite tables: `articles`, `publications`, `stats`, `schema_version`. WAL mode, foreign keys ON.
- **YAML migration**: `migrate_yaml_to_sqlite(yaml_path, db_path)` migrates a v2 YAML registry to the SQLite schema; renames the YAML to `.bak`.

**MCP Server** (`mcp_server.py`, ~1100 lines): Full CLI parity for Claude Code via Model Context Protocol.
- Started via `crier mcp` (stdio) or `crier mcp --http` (SSE)
- **17 tools** in 4 categories:
  - Registry: `crier_query`, `crier_missing`, `crier_article`, `crier_publications`, `crier_record`, `crier_failures`, `crier_summary`, `crier_sql`
  - Content: `crier_search`, `crier_check`
  - Actions: `crier_publish`, `crier_delete`, `crier_archive`
  - Platform: `crier_list_remote`, `crier_doctor`, `crier_stats`, `crier_stats_refresh`
- **3 resources**: `crier://schema`, `crier://config` (sanitized), `crier://platforms` (capabilities + modes)
- **Two-step confirmation** for destructive ops (`crier_publish`, `crier_delete`):
  - Step 1: call without `confirmation_token` to get a preview + token (5-min TTL)
  - Step 2: call with `confirmation_token` to execute
  - **Critical invariant: step 2 treats the token as source of truth.** All parameters (file, platform, rewrite_content, key, target_platforms) come from the token. Caller args on step 2 are ignored. This prevents a token-substitution bypass where a caller could get a token for operation A and use it to authorize operation B. See `_create_token` / `_consume_token` in `mcp_server.py`.
- `crier_sql` runs queries inside a `SAVEPOINT crier_sql_guard` that is always rolled back, so even non-SELECT statements have no effect (defense in depth on top of `startswith("SELECT")`).
- All tools return **dicts** (FastMCP serializes them); validation errors return `{"error": "..."}`.
- Tools use lazy imports (`from .X import Y` inside functions) for fast MCP startup and to avoid circular imports.
- Built on `mcp.server.fastmcp.FastMCP`.

**Converters** (`converters/markdown.py`): Parses markdown files with YAML or TOML front matter into `Article` objects. Automatically resolves relative links (e.g., `/posts/other/`) to absolute URLs using `site_base_url` so they work on cross-posted platforms.

**Utils** (`utils.py`): Shared pure utility functions (no CLI dependencies):
- `truncate_at_sentence()` — Smart text truncation at sentence/word boundaries
- `find_content_files()` — Discover content files using config paths/patterns
- `parse_date_filter()` — Parse relative/absolute date strings
- `get_content_date()` / `get_content_tags()` — Extract front matter metadata

**Rewrite** (`rewrite.py`): Auto-rewrite orchestration for platform content adaptation:
- `auto_rewrite_for_platform()` — LLM retry loop with configurable retries and truncation fallback
- `AutoRewriteResult` dataclass for structured success/failure results

**Skill** (`skill.py`): Claude Code skill installation (deprecated). Loads `SKILL.md` from package resources and installs to `~/.claude/skills/crier/`. Superseded by the crier Claude Code plugin available from the queelius-plugins marketplace.

**Crier Plugin** (separate repo at `~/github/alex-claude-plugins/crier/`): the user-facing Claude Code integration. Composed of:
- `skills/crier/SKILL.md`: judgment context (rewrite voice, platform culture). Intentionally short (~90 lines); MCP tools are self-describing so the skill doesn't repeat the CLI reference.
- `commands/crier.md`: the `/crier` slash command for interactive workflows.
- `agents/cross-poster.md`: autonomous bulk-publishing agent. Calls MCP tools directly (not Bash).
- `agents/auditor.md`: read-only analysis agent (gap analysis, performance review, staleness, failure triage).
- `.mcp.json`: registers the `crier mcp` stdio server with the plugin.

## Key Features

- **Dry run mode**: Preview before publishing with `--dry-run`
- **Publishing profiles**: Group platforms (e.g., `--profile blogs`)
- **Publication tracking**: SQLite registry tracks what's been published where (slug-keyed)
- **MCP server**: `crier mcp` exposes registry to Claude Code for queries and automation
- **Audit & bulk publish**: Find and publish missing content with `audit --publish`
- **Bulk operation filters**:
  - `--only-api` — Skip manual/import platforms
  - `--long-form` — Skip short-form platforms (bluesky, mastodon, twitter, threads)
  - `--tag <tag>` — Only include content with matching tags (case-insensitive, OR logic)
  - `--sample N` — Random sample of N items
  - `--include-archived` — Include archived content
  - `--since` / `--until` — Date filtering (supports `1d`, `1w`, `1m`, `1y` or `YYYY-MM-DD`)
- **Manual mode**: Copy-paste mode for platforms without API access (`--manual` or `api_key: manual`)
- **Import mode**: URL import for platforms like Medium (`api_key: import`)
- **Rewrites**: Custom short-form content with `--rewrite` for social platforms
- **Auto-rewrite**: LLM-generated rewrites with `--auto-rewrite` (requires LLM config)
- **Batch mode**: Non-interactive automation with `--batch` (implies `--yes --json`, skips manual platforms)
- **JSON output**: Machine-readable output with `--json` for CI/CD integration
- **Doctor**: Validate all API keys work (`--json` for scripting)
- **RSS/Atom feeds**: Generate feeds from content with `crier feed` (`--format atom`, `--output`, `--limit`, `--tag`)
- **Retry & rate limiting**: All platform API calls use centralized retry with exponential backoff (429, 502-504, timeouts)
- **Error tracking**: Failed publications are recorded and can be retried with `audit --retry`
- **SQLite registry**: WAL-mode SQLite with slug primary keys (no YAML, no content hashes)
- **Stats comparison**: `crier stats --compare` shows cross-platform engagement side-by-side
- **Relative link resolution**: Converts relative links (`/posts/other/`, `../images/`) to absolute URLs using `site_base_url`
- **Delete/Archive**: Remove content from platforms (`crier delete`) or exclude from audit (`crier archive`)
- **Scheduling**: Schedule posts for future publication with `--schedule` or `crier schedule` commands
- **Analytics**: Track engagement stats across platforms with `crier stats`
- **Threading**: Split long content into threads for Bluesky/Mastodon with `--thread`

## Automation Modes

**Batch mode** (`--batch`): Fully automated, non-interactive publishing for CI/CD:
```bash
# Batch mode implies --yes --json, skips manual/import platforms
crier publish article.md --to devto --to bluesky --batch
crier audit --publish --batch --long-form
```

**JSON output** (`--json`): Machine-readable output for parsing:
```bash
crier publish article.md --to devto --json
crier audit --json
```

**Quiet mode** (`--quiet`): Suppress non-essential output for scripting:
```bash
# Quiet mode suppresses progress/info messages
crier publish article.md --to devto --quiet
crier audit --publish --yes --quiet
crier search --tag python --quiet
```

**Config access** (`config get`): Read config values programmatically:
```bash
crier config get llm.model
crier config get platforms.devto.api_key
crier config get site_base_url --json
```

**Non-interactive flags**:
- `--yes` / `-y` — Skip confirmation prompts (available on `publish`, `audit --publish`, `register`)
- `--quiet` / `-q` — Suppress non-essential output (available on `publish`, `audit`, `search`)

**Auto-rewrite** (`--auto-rewrite`): LLM-generated short-form content:
```bash
# Configure LLM first (see LLM Configuration below)
crier publish article.md --to bluesky --auto-rewrite

# Preview rewrite with dry-run (invokes LLM, shows preview with char budget)
crier publish article.md --to bluesky --auto-rewrite --dry-run

# Disable auto-rewrite explicitly
crier publish article.md --to bluesky --no-auto-rewrite

# Retry up to 3 times if output exceeds character limit
crier publish article.md --to bluesky --auto-rewrite --auto-rewrite-retry 3
# Or use short form: -R 3

# Truncate at sentence boundary if all retries fail
crier publish article.md --to bluesky --auto-rewrite -R 3 --auto-rewrite-truncate

# Override temperature (0.0-2.0, higher=more creative)
crier publish article.md --to bluesky --auto-rewrite --temperature 1.2

# Override model for this publish
crier publish article.md --to bluesky --auto-rewrite --model gpt-4o
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success - all operations completed |
| 1 | Failure - operation failed or validation error |
| 2 | Partial - some operations succeeded, some failed |

```bash
# Check exit code in scripts
crier publish article.md --to devto --batch
echo "Exit code: $?"

# Example: retry on partial failure
crier audit --publish --batch
if [ $? -eq 2 ]; then
  echo "Some platforms failed, retry needed"
fi
```

## LLM Configuration

For `--auto-rewrite` to work:

**Simplest:** Just have `OPENAI_API_KEY` env var set (defaults to gpt-4o-mini).

**Or configure in `~/.config/crier/config.yaml`:**

```yaml
# Minimal (defaults to OpenAI + gpt-4o-mini)
llm:
  api_key: sk-...

# Full config for Ollama/other providers
llm:
  base_url: http://localhost:11434/v1
  model: llama3

# Full config with retry and truncation defaults
llm:
  api_key: sk-...
  base_url: https://api.openai.com/v1
  model: gpt-4o-mini
  temperature: 0.7          # Default: 0.7 (0.0-2.0, higher=more creative)
  retry_count: 0            # Default: 0 (no retries)
  truncate_fallback: false  # Default: false (no hard truncation)
```

**Set config via CLI:**
```bash
crier config llm set temperature 0.9
crier config llm set retry_count 3
crier config llm set truncate_fallback true
```

**View and test LLM config:**
```bash
# View current LLM configuration
crier config llm show

# Test the LLM connection with a simple request
crier config llm test
```

**Environment variables** (override config):
- `OPENAI_API_KEY` — API key (auto-defaults to OpenAI endpoint + gpt-4o-mini)
- `OPENAI_BASE_URL` — Custom endpoint (e.g., `http://localhost:11434/v1` for Ollama)

## Bulk Operations

Filter order: path → date → platform mode → content type → tag → sampling

**Bulk operation filters**:
- `--only-api` — Skip manual/import platforms
- `--long-form` — Skip short-form platforms (bluesky, mastodon, twitter, threads)
- `--tag <tag>` — Only include content with matching tags (case-insensitive, OR logic)
- `--sample N` — Random sample of N items
- `--since` / `--until` — Date filtering (supports `1d`, `1w`, `1m`, `1y` or `YYYY-MM-DD`)
- `--date-source` — Filter by `frontmatter` (default) or `mtime`

```bash
# Fully automated batch mode
crier audit --publish --batch --long-form

# Typical bulk publish
crier audit --publish --yes --only-api --long-form

# Filter by tag (only technical posts)
crier audit --tag python --tag algorithms --only-api --publish --yes

# Sample recent content
crier audit --since 1m --sample 10 --publish --yes

# Date range
crier audit --since 2025-01-01 --until 2025-01-31 --publish --yes

# Path + filters
crier audit content/post --since 1w --only-api --long-form --publish --yes

# Combine tag filter with other filters
crier audit --tag machine-learning --since 1m --long-form --publish --yes
```

## Content Search

Search and explore content without publishing using `crier search`:

```bash
# List all content
crier search

# Filter by tag
crier search --tag python

# Filter by date
crier search --since 1m

# Combine filters
crier search content/post --tag python --since 1w

# JSON for scripting
crier search --tag python --json | jq '.results[].file'

# Sample random posts
crier search --sample 5
```

JSON output includes: file, title, date, tags, word count.

## Delete & Archive

```bash
# Delete from specific platform
crier delete article.md --from devto

# Delete from all platforms
crier delete article.md --all

# Archive (exclude from audit --publish)
crier archive article.md

# Unarchive
crier unarchive article.md

# Include archived in audit
crier audit --include-archived
```

## Scheduling

```bash
# Schedule a post for later
crier publish article.md --to devto --schedule "tomorrow 9am"

# Manage scheduled posts
crier schedule list
crier schedule show ID
crier schedule cancel ID
crier schedule run                      # Publish all due posts
```

Schedule data stored in `<site_root>/.crier/schedule.yaml`.

## Analytics

```bash
# Stats for all content
crier stats

# Stats for specific file
crier stats article.md
crier stats article.md --refresh        # Force refresh from API

# Top articles by engagement
crier stats --top 10
crier stats --since 1m --json

# Filter by platform
crier stats --platform devto
```

Stats cached in registry for 1 hour. Platforms with stats: devto (views, likes, comments), bluesky (likes, comments, reposts), mastodon (likes, comments, reposts), linkedin (likes, comments), threads (views, likes, replies, reposts).

```bash
# Compare engagement across platforms for same content
crier stats --compare

# Export stats to CSV
crier stats --export csv
```

## RSS/Atom Feeds

```bash
# Generate RSS feed to stdout
crier feed

# Write to file
crier feed --output feed.xml

# Atom format
crier feed --format atom

# Filter and limit
crier feed --limit 10 --tag python
crier feed --since 1m --until 1w
```

Requires `site_base_url` to be configured. Uses `feedgen` library for valid RSS 2.0 and Atom XML.

## Error Recovery

```bash
# View failed publications
crier audit --failed

# Re-attempt failed publications
crier audit --retry

# Preview what would be retried
crier audit --retry --dry-run

# JSON output for scripting
crier audit --failed --json
```

Failed publications are automatically recorded in the registry with error details and timestamp. Successful re-publish clears the error.

## Threading

```bash
# Split content into thread
crier publish article.md --to bluesky --thread

# Thread styles
crier publish article.md --to mastodon --thread --thread-style numbered  # 1/5, 2/5...
crier publish article.md --to bluesky --thread --thread-style emoji      # 🧵 1/5...
crier publish article.md --to mastodon --thread --thread-style simple    # No prefix
```

Thread splitting priority: manual markers (`<!-- thread -->`) → paragraph boundaries → sentence boundaries. Supported platforms: bluesky, mastodon.

## Pre-Publish Validation

```bash
# Check a single file
crier check article.md

# Check with platform context
crier check article.md --to bluesky --to devto

# Check all content
crier check --all

# Strict mode: warnings become errors
crier check article.md --strict

# Check external links (slow, opt-in)
crier check article.md --check-links

# JSON output
crier check article.md --json
```

**Checks performed:**
- Front matter: missing-title (error), missing-date (warning), future-date (info), missing-tags (warning), empty-tags (warning), title-length (warning), missing-description (info)
- Content: empty-body (error), short-body (warning), broken-relative-links (warning), image-alt-text (info)
- Platform-specific: bluesky-length (warning), mastodon-length (warning), devto-canonical (info)
- External: broken-external-link (warning, opt-in with `--check-links`)

**Publish integration:** Pre-publish checks run automatically. Use `--no-check` to skip, `--strict` to block on warnings.

**Audit integration:** Use `--check` with `--publish` to skip files that fail validation.

**Configure severity overrides** in `~/.config/crier/config.yaml`:
```yaml
checks:
  missing-tags: disabled    # Don't care about tags
  missing-date: error       # Promote to error
  short-body: disabled      # Allow short posts
```

## Non-Obvious Conventions

These conventions are not visible from reading any single file. Violating them will cause regressions.

**Token-as-source-of-truth (MCP destructive ops).** In `crier_publish` and `crier_delete`, step 2 reads ALL operation parameters from the consumed token. Caller arguments on step 2 are intentionally ignored. This prevents a token-substitution bypass. If you add a new parameter to step 1, you MUST add it to the token's `details` dict and read it back in step 2. See `_create_token` / `_consume_token` in `mcp_server.py` and the `test_*_step2_token_overrides_caller_args` regression tests.

**`_resolve_slug` dual-key dispatch.** Every public registry function that takes a "key" parameter (named `canonical_url` for backwards compat) actually accepts either a slug or a canonical_url. Internally it goes through `_resolve_slug(conn, key)` which tries the slug primary-key lookup first. Do not assume the parameter is one or the other; use it as opaque.

**Failure rows masquerade as publications.** `record_failure` writes a row to the `publications` table with `platform_id IS NULL`. SQL queries that want "real" publications must filter `WHERE platform_id IS NOT NULL AND deleted_at IS NULL`. Forgetting this filter will count failed attempts as successful publications.

**UPSERT, not `INSERT OR REPLACE`.** `INSERT OR REPLACE` triggers `ON DELETE CASCADE` on the stats table and silently resets unlisted columns. Use `INSERT ... ON CONFLICT DO UPDATE SET` and explicitly list every column that should reset on conflict (`deleted_at = NULL`, `last_error = NULL`, etc.). Locked in by `TestDeletionPreservesHistory` regression tests.

**Lazy imports in `mcp_server.py`.** Top-level imports are kept minimal so MCP startup is fast (tool-list time matters). Most module imports happen inside tool functions. This is intentional, not laziness.

**Article reconstruction via `dataclasses.replace`.** When applying a rewrite to an `Article`, use `_apply_rewrite(article, content)` (in `mcp_server.py`) or `dataclasses.replace(article, body=..., is_rewrite=True)` directly. Manually constructing `Article(...)` will silently drop fields if `Article` ever grows new attributes.

**Short-form platform detection via class attribute.** `is_short_form_platform(name)` reads `PLATFORMS[name].is_short_form` (a class attribute on the `Platform` subclass). User plugins opt in by setting `is_short_form = True` on their class. Do NOT add a hardcoded set in `config.py`.

**Registry path is global, content paths are per-site.** `get_db_path()` returns `~/.config/crier/crier.db` (overridable via `CRIER_DB`). `get_content_paths()` returns paths relative to `get_project_root()` (which is `site_root` from config, not CWD). Don't conflate them.

**No `.crier/registry.yaml`.** The registry is SQLite. Old YAML registries can be migrated via `migrate_yaml_to_sqlite()` from `registry.py`.

## Adding a New Platform

1. Create `platforms/newplatform.py` implementing the `Platform` abstract class
2. Set class attributes: `name`, `description`, `max_content_length`, `supports_delete`, `supports_stats`, `supports_threads`
3. Implement required methods: `publish`, `update`, `list_articles`, `get_article`
4. Use `self.retry_request(method, url, **kwargs)` instead of direct `requests.*()` calls
5. Optionally implement: `delete` → `DeleteResult`, `get_stats` → `ArticleStats`, `publish_thread` → `ThreadPublishResult`
6. Register in `platforms/__init__.py` by adding to `PLATFORMS` dict
7. Update README.md with API key format

### Adding a Mastodon-API-Compatible Server (Pleroma, Akkoma, GoToSocial, ...)

If the new platform implements Mastodon's REST API (most fediverse servers do), inherit from `FediversePlatform` instead of `Platform` and override only the class attributes that differ:

```python
from ._fediverse import FediversePlatform

class Akkoma(FediversePlatform):
    name = "akkoma"
    description = "Short posts on Akkoma fediverse server"
    max_content_length = 5000  # adjust per your instance
    default_instance = None    # users configure per their instance
```

All request logic (publish, update, list, delete, threads, stats, HTML stripping) is inherited unchanged. Servers that do NOT implement Mastodon's API (Lemmy, PeerTube) need their own platform classes deriving directly from `Platform`.

### Hidden base classes (leading underscore)

Files in `platforms/` that start with `_` are skipped by auto-discovery. Use this for shared base classes that are not themselves user-visible platforms (currently `_fediverse.py`). The class is still importable via standard Python imports; only the registry-builder ignores it.

### User Plugins

Users can add custom platforms without modifying the crier source:

1. Create `~/.config/crier/platforms/` directory
2. Drop a `.py` file implementing `Platform` from `crier.platforms.base`
3. Set `name` class attribute (used as platform identifier)
4. Implement required methods: `publish`, `update`, `list_articles`, `get_article`
5. Configure API key: `crier config set platforms.<name>.api_key <key>`

User plugins are auto-discovered at import time. If a user plugin has the same `name` as a built-in, the user plugin wins. Files starting with `_` are skipped. Broken plugins warn but don't crash.

Discovery is handled by `_discover_user_platforms()` in `platforms/__init__.py`, which scans `USER_PLATFORMS_DIR = Path.home() / ".config" / "crier" / "platforms"`. Multiple `Platform` subclasses per file are supported. If the `name` attribute is not overridden (still `"base"`), the lowercase class name is used instead.

## Testing

Tests are in `tests/` with 1244 tests covering config, registry, converters, CLI, platforms, scheduler, stats, threading, checker, utils, rewrite, feed, skill, MCP (62 tests), plugin discovery, and the Fediverse abstraction (26 tests).

**Running tests:**
```bash
pytest                          # All tests
pytest tests/test_cli.py -v     # Single file
pytest -k "test_publish" -v     # By name pattern
pytest --cov=crier              # With coverage
```

**Key fixtures** (in `conftest.py`):
- `sample_article` — Pre-built `Article` object
- `sample_markdown_file` — Temp markdown file with front matter
- `tmp_config` — Isolated config environment (patches `DEFAULT_CONFIG_FILE`)
- `tmp_registry` — Isolated SQLite registry (`CRIER_DB` env var + `reset_connection()` + `init_db()`)
- `mock_env_api_key` — Factory to set `CRIER_{PLATFORM}_API_KEY` env vars
- `configured_platforms` — Config with devto, bluesky, twitter (manual), profiles

**Test isolation for registry:** Every test that touches the registry MUST set `CRIER_DB` to a temp path, call `reset_connection()`, and `init_db()`. The `tmp_registry` fixture handles this. Local overrides exist in `test_stats.py` and `test_threading.py`.

Platform tests mock `requests` calls rather than hitting real APIs.
