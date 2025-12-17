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

# Build and serve docs locally
mkdocs serve
```

## Architecture

**CLI Layer** (`cli.py`): Click-based commands that orchestrate the workflow:
- `publish` — Publish to platforms (supports `--dry-run`, `--profile`)
- `status` — Show publication status for files
- `audit` — Check what's missing from platforms
- `backfill` — Publish missing content
- `doctor` — Validate API keys
- `config` — Manage API keys and profiles

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

## Key Features

- **Dry run mode**: Preview before publishing with `--dry-run`
- **Publishing profiles**: Group platforms (e.g., `--profile blogs`)
- **Publication tracking**: Registry tracks what's published where
- **Audit & backfill**: Find and publish missing content
- **Doctor**: Validate all API keys work

## Adding a New Platform

1. Create `platforms/newplatform.py` implementing the `Platform` abstract class
2. Register in `platforms/__init__.py` by adding to `PLATFORMS` dict
3. Add documentation in `docs/platforms/newplatform.md`
4. Update README.md with API key format

## Documentation

Documentation is in `docs/` using MkDocs with Material theme. Deployed to GitHub Pages via `.github/workflows/docs.yml`.

## Testing Notes

Tests directory exists but is currently empty. When adding tests:
- Use pytest fixtures for mocking API responses
- Test both success and failure paths for platform operations
- Mock `requests` calls rather than hitting real APIs
