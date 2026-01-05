# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Crier is a CLI tool for cross-posting content to multiple platforms. It reads markdown files with YAML front matter and publishes them via platform APIs. Designed to be used with Claude Code for automated content distribution.

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
- `publish` — Publish to platforms (supports `--dry-run`, `--profile`, `--manual`, `--rewrite`, `--auto-rewrite`, `--batch`, `--json`)
- `status` — Show publication status for files
- `audit` — Check what's missing/changed (supports bulk operations with filters, `--batch`, `--json`)
- `doctor` — Validate API keys
- `config` — Manage API keys, profiles, and content paths
- `skill` — Manage Claude Code skill installation (`install`, `uninstall`, `status`, `show`)
- `register` / `unregister` — Manual registry management
- `list` — List articles on a platform

**LLM Module** (`llm/`): Optional auto-rewrite using OpenAI-compatible APIs:
- `provider.py`: Abstract `LLMProvider` interface and `RewriteResult` dataclass
- `openai_compat.py`: `OpenAICompatProvider` for OpenAI, Ollama, Groq, etc.

**Platform Abstraction** (`platforms/`):
- `base.py`: Abstract `Platform` class defining the interface (`publish`, `update`, `list_articles`, `get_article`, `delete`) and core data classes (`Article`, `PublishResult`)
- Each platform implements the `Platform` interface
- `PLATFORMS` registry in `__init__.py` maps platform names to classes

**Platform Categories** (13 total):
- Blog: devto, hashnode, medium, ghost, wordpress
- Newsletter: buttondown
- Social: bluesky, mastodon, linkedin, threads, twitter (copy-paste mode)
- Announcement: telegram, discord

**Config** (`config.py`): Two-tier configuration system:
- **Global** (`~/.config/crier/config.yaml`): API keys and profiles, shared across projects
- **Local** (`.crier/config.yaml`): Project-specific settings (content_paths, site_base_url, exclude_patterns, file_extensions, default_profile, rewrite_author)
- Environment variables (`CRIER_{PLATFORM}_API_KEY`) take precedence over config files
- Supports composable profiles (profiles can reference other profiles)

**Registry** (`registry.py`): Tracks publications in `.crier/registry.yaml`. Records what's been published where, enables status checks, audit, and backfill.

**Converters** (`converters/markdown.py`): Parses markdown files with YAML front matter into `Article` objects.

**Skill** (`skill.py`): Claude Code skill installation. Loads `SKILL.md` from package resources and installs to `~/.claude/skills/crier/`.

## Key Features

- **Dry run mode**: Preview before publishing with `--dry-run`
- **Publishing profiles**: Group platforms (e.g., `--profile blogs`)
- **Publication tracking**: Registry tracks what's published where
- **Audit & bulk publish**: Find and publish missing content with `audit --publish`
- **Bulk operation filters**:
  - `--only-api` — Skip manual/import platforms
  - `--long-form` — Skip short-form platforms (bluesky, mastodon, twitter, threads)
  - `--sample N` — Random sample of N items
  - `--include-changed` — Also update changed content
  - `--since` / `--until` — Date filtering (supports `1d`, `1w`, `1m`, `1y` or `YYYY-MM-DD`)
- **Manual mode**: Copy-paste mode for platforms without API access (`--manual` or `api_key: manual`)
- **Import mode**: URL import for platforms like Medium (`api_key: import`)
- **Rewrites**: Custom short-form content with `--rewrite` for social platforms
- **Auto-rewrite**: LLM-generated rewrites with `--auto-rewrite` (requires LLM config)
- **Batch mode**: Non-interactive automation with `--batch` (implies `--yes --json`, skips manual platforms)
- **JSON output**: Machine-readable output with `--json` for CI/CD integration
- **Doctor**: Validate all API keys work

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

**Auto-rewrite** (`--auto-rewrite`): LLM-generated short-form content:
```bash
# Configure LLM first (see LLM Configuration below)
crier publish article.md --to bluesky --auto-rewrite
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
```

**Environment variables** (override config):
- `OPENAI_API_KEY` — Auto-configures OpenAI endpoint + gpt-4o-mini
- `CRIER_LLM_API_KEY`, `CRIER_LLM_BASE_URL`, `CRIER_LLM_MODEL` — Explicit overrides

## Bulk Operations

Filter order: path → date → platform mode → content type → changed → sampling

```bash
# Fully automated batch mode
crier audit --publish --batch --long-form

# Typical bulk publish
crier audit --publish --yes --only-api --long-form

# Sample recent content
crier audit --since 1m --sample 10 --publish --yes

# Date range
crier audit --since 2025-01-01 --until 2025-01-31 --publish --yes

# Path + filters
crier audit content/post --since 1w --only-api --long-form --publish --yes
```

## Adding a New Platform

1. Create `platforms/newplatform.py` implementing the `Platform` abstract class
2. Register in `platforms/__init__.py` by adding to `PLATFORMS` dict
3. Update README.md with API key format

## Testing

Tests are in `tests/` with ~1800 lines covering config, registry, converters, CLI, and platforms.

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
- `tmp_registry` — Isolated registry in temp directory
- `mock_env_api_key` — Factory to set `CRIER_{PLATFORM}_API_KEY` env vars
- `configured_platforms` — Config with devto, bluesky, twitter (manual), profiles

Platform tests mock `requests` calls rather than hitting real APIs.
