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
- `publish` — Publish to platforms (supports `--dry-run`, `--profile`, `--manual`, `--rewrite`)
- `status` — Show publication status for files
- `audit` — Check what's missing from platforms (supports `--publish` for bulk operations)
- `doctor` — Validate API keys
- `config` — Manage API keys, profiles, and content paths
- `skill` — Manage Claude Code skill installation (`install`, `uninstall`, `status`, `show`)

**Platform Abstraction** (`platforms/`):
- `base.py`: Abstract `Platform` class defining the interface (`publish`, `update`, `list_articles`, `get_article`, `delete`) and core data classes (`Article`, `PublishResult`)
- Each platform implements the `Platform` interface
- `PLATFORMS` registry in `__init__.py` maps platform names to classes

**Platform Categories** (13 total):
- Blog: devto, hashnode, medium, ghost, wordpress
- Newsletter: buttondown
- Social: bluesky, mastodon, linkedin, threads, twitter (copy-paste mode)
- Announcement: telegram, discord

**Config** (`config.py`): API keys and profiles stored in `~/.config/crier/config.yaml` or via `CRIER_{PLATFORM}_API_KEY` environment variables. Environment variables take precedence. Supports composable profiles.

**Registry** (`registry.py`): Tracks publications in `.crier/registry.yaml`. Records what's been published where, enables status checks, audit, and backfill.

**Converters** (`converters/markdown.py`): Parses markdown files with YAML front matter into `Article` objects.

**Skill** (`skill.py`): Claude Code skill installation. Installs `SKILL.md` to `~/.claude/skills/crier/` for Claude Code integration.

## Key Features

- **Dry run mode**: Preview before publishing with `--dry-run`
- **Publishing profiles**: Group platforms (e.g., `--profile blogs`)
- **Publication tracking**: Registry tracks what's published where
- **Audit & publish**: Find and publish missing content with `audit --publish`
- **Manual mode**: Copy-paste mode for platforms without API access (`--manual` or `api_key: manual`)
- **Rewrites**: Custom short-form content with `--rewrite` for social platforms
- **Doctor**: Validate all API keys work

## Adding a New Platform

1. Create `platforms/newplatform.py` implementing the `Platform` abstract class
2. Register in `platforms/__init__.py` by adding to `PLATFORMS` dict
3. Update README.md with API key format

## Testing Notes

Tests directory exists but is currently empty. When adding tests:
- Use pytest fixtures for mocking API responses
- Test both success and failure paths for platform operations
- Mock `requests` calls rather than hitting real APIs
