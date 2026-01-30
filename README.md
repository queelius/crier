# Crier

Cross-post your content to dev.to, Ghost, WordPress, Hashnode, Medium, Bluesky, Mastodon, Threads, Telegram, Discord, and more.

Like a town crier announcing your content to the world.

## Getting Started

### Quick Setup

```bash
pip install crier
cd your-blog
crier init
```

The `init` command walks you through:
- Creating the `.crier/` registry directory
- Detecting your content directories
- Configuring platforms with API keys

### How It Works

1. **Your markdown posts** with YAML front matter are the source of truth
2. **`.crier/registry.yaml`** tracks what's published where
3. **`crier audit`** shows what's missing or changed
4. **`crier publish`** or `audit --publish` publishes content

```bash
# See what needs publishing
crier audit

# Publish a file to a platform
crier publish post.md --to devto

# Publish to multiple platforms
crier publish post.md --to devto --to bluesky --to mastodon

# Bulk publish missing content (interactive)
crier audit --publish
```

### With Claude Code

Crier is designed to work with Claude Code for AI-assisted publishing.
Install the skill with `crier skill install`, then just ask Claude naturally:

- "Cross-post my latest article to all platforms"
- "What articles haven't been published to Bluesky?"
- "Publish this post to Mastodon with a good announcement"

Claude automatically detects when to use the crier skill and follows
the workflow: audit, select, publish (with rewrites for short-form platforms).

## Installation

```bash
pip install crier
```

## Supported Platforms

| Platform | API Key Format | Notes |
|----------|---------------|-------|
| **dev.to** | `api_key` | Full article support |
| **Hashnode** | `token` or `token:publication_id` | Full article support |
| **Medium** | `integration_token` | Publish only (no edit/list) |
| **Ghost** | `https://site.com:key_id:key_secret` | Full article support |
| **WordPress** | `site.wordpress.com:token` or `https://site.com:user:app_pass` | Full article support |
| **Buttondown** | `api_key` | Newsletter publishing |
| **Bluesky** | `handle:app_password` | Short posts with link cards |
| **Mastodon** | `instance:access_token` | Toots with hashtags |
| **Threads** | `user_id:access_token` | Short posts (no edit support) |
| **Telegram** | `bot_token:chat_id` | Channel/group posts |
| **Discord** | `webhook_url` | Server announcements |
| **LinkedIn** | `access_token` | Requires API access |
| **Twitter/X** | `any` (copy-paste mode) | Generates tweet for manual posting |

### Platform Notes

**Blog Platforms** (dev.to, Hashnode, Medium, Ghost, WordPress):
- Full markdown article publishing
- Preserves front matter (title, description, tags, canonical_url)
- Best for long-form content

**Newsletter Platforms** (Buttondown):
- Publishes to email subscribers
- Full markdown support
- Great for content repurposing

**Social Platforms** (Bluesky, Mastodon, LinkedIn, Twitter, Threads):
- Creates short posts with link to canonical URL
- Uses title + description + hashtags from tags
- Best for announcing new content

**Announcement Channels** (Telegram, Discord):
- Posts to channels/servers
- Good for community announcements
- Discord uses webhook embeds

### Manual Mode

For platforms with restrictive API access (Medium, LinkedIn, Twitter/X), you can use manual (copy-paste) mode:

```bash
# Explicit manual mode with --manual flag
crier publish post.md --to medium --manual
crier publish post.md --to linkedin --manual

# Skip auto-opening browser
crier publish post.md --to twitter --manual --no-browser
```

**Auto-manual mode**: If you configure a platform's API key to `"manual"`, crier automatically uses manual mode:

```bash
# Configure platform for manual mode (no API key needed)
crier config set twitter.api_key manual
crier config set linkedin.api_key manual

# Now these automatically use manual mode without --manual flag
crier publish post.md --to twitter
crier publish post.md --to linkedin
```

Manual mode workflow:
1. Formats content for the platform
2. Copies it to your clipboard
3. Opens the compose page in your browser
4. Asks if you successfully posted
5. Records to registry only if you confirm

This ensures the registry accurately reflects what's actually published.

## Configuration

Crier uses two configuration files:

### Global Config (`~/.config/crier/config.yaml`)

API keys and profiles (shared across all projects):

```yaml
platforms:
  devto:
    api_key: your_key_here
  bluesky:
    api_key: "handle.bsky.social:app-password"
  mastodon:
    api_key: "mastodon.social:access-token"
  twitter:
    api_key: manual    # Copy-paste mode
  medium:
    api_key: import    # URL import mode

profiles:
  blogs:
    - devto
    - hashnode
    - medium
  social:
    - bluesky
    - mastodon
  everything:
    - blogs           # Profiles can reference other profiles
    - social
```

### Local Config (`.crier/config.yaml`)

Project-specific settings:

```yaml
content_paths:
  - content                    # Directories to scan for markdown files
site_base_url: https://yoursite.com
exclude_patterns:
  - _index.md                  # Files to skip (Hugo section pages)
file_extensions:
  - .md
  - .mdx                       # Optional: for MDX content
default_profile: everything    # Used when no --to or --profile specified
rewrite_author: claude-code    # Default author for AI-generated rewrites
```

| Option | Purpose |
|--------|---------|
| `content_paths` | Directories to scan for content |
| `site_base_url` | For inferring canonical URLs |
| `exclude_patterns` | Filename patterns to skip |
| `file_extensions` | Extensions to scan (default: `.md`) |
| `default_profile` | Default platforms when none specified |
| `rewrite_author` | Default `--rewrite-author` value |

### Environment Variables

Environment variables override config files:

```bash
export CRIER_DEVTO_API_KEY=your_key_here
export CRIER_BLUESKY_API_KEY="handle.bsky.social:app-password"
```

## Markdown Format

Crier reads standard markdown with YAML or TOML front matter:

```markdown
---
title: "My Amazing Post"
description: "A brief description"
tags: [python, programming]
canonical_url: https://myblog.com/my-post
published: true
---

Your content here...
```

TOML front matter is also supported (delimited by `+++`):

```markdown
+++
title = "My Amazing Post"
description = "A brief description"
tags = ["python", "programming"]

[extra]
canonical_url = "https://myblog.com/my-post"
+++

Your content here...
```

## Commands

```bash
# Publishing
crier init                              # Interactive setup wizard
crier publish FILE --to PLATFORM        # Publish to platform(s)
crier publish FILE --to PLATFORM --manual  # Manual copy-paste mode
crier publish FILE --to bluesky --thread   # Publish as thread
crier audit                             # See what's missing/changed
crier audit --publish                   # Bulk publish interactively
crier audit --publish --yes             # Bulk publish without prompting

# Content Management
crier search                            # List all content
crier search --tag python --since 1w    # Filter by tag and date
crier status [FILE]                     # Show publication status
crier list PLATFORM                     # List your articles
crier delete FILE --from PLATFORM       # Delete from platform
crier archive FILE                      # Archive (exclude from audit)
crier unarchive FILE                    # Unarchive

# Scheduling
crier schedule list                     # List scheduled posts
crier schedule show ID                  # Show scheduled post details
crier schedule cancel ID                # Cancel scheduled post
crier schedule run                      # Publish due posts

# Analytics
crier stats                             # Show stats for all content
crier stats FILE                        # Show stats for specific file
crier stats --top 10                    # Top 10 by engagement
crier stats --refresh                   # Refresh from platforms

# Configuration
crier config show                       # Show configuration
crier config set KEY VALUE              # Set configuration
crier config llm show                   # Show LLM configuration
crier config llm test                   # Test LLM connection
crier doctor                            # Verify API keys work
crier skill install                     # Install Claude Code skill
```

## Automation

### Batch Mode

Use `--batch` for fully automated, non-interactive publishing (CI/CD):

```bash
# Batch mode implies --yes --json, skips manual/import platforms
crier publish post.md --to devto --to bluesky --batch
crier audit --publish --batch --long-form
```

Batch mode behavior:
- Implies `--yes` (no confirmation prompts)
- Implies `--json` (structured output for parsing)
- Implies `--only-api` (skips manual/import platforms that require user interaction)

### JSON Output

Use `--json` for machine-readable output:

```bash
crier publish post.md --to devto --json
crier audit --json
```

JSON output structure:
```json
{
  "command": "publish",
  "file": "post.md",
  "results": [{"platform": "devto", "success": true, "url": "..."}],
  "summary": {"succeeded": 1, "failed": 0, "skipped": 0}
}
```

### Auto-Rewrite

Use `--auto-rewrite` to generate short-form content using an LLM:

```bash
crier publish post.md --to bluesky --auto-rewrite
```

**Simplest setup:** If you have `OPENAI_API_KEY` set, it just works (defaults to gpt-4o-mini).

**Or configure in `~/.config/crier/config.yaml`:**

```yaml
# Minimal - just the API key (defaults to OpenAI + gpt-4o-mini)
llm:
  api_key: sk-...

# Or full config for Ollama/other providers
llm:
  base_url: http://localhost:11434/v1  # Ollama
  model: llama3
  # api_key: not needed for local Ollama
```

**Environment variables** (override config):
- `OPENAI_API_KEY` — API key (auto-defaults to OpenAI endpoint + gpt-4o-mini)
- `OPENAI_BASE_URL` — Custom endpoint (e.g., `http://localhost:11434/v1` for Ollama)

## Bulk Operations

The `audit` command supports powerful filtering for targeted bulk operations:

```bash
# Post to API platforms only (skip manual/import)
crier audit --publish --yes --only-api

# Long-form only (skip bluesky, mastodon, twitter, threads)
crier audit --publish --yes --long-form

# Random sample of 5 articles
crier audit --publish --yes --sample 5

# Include changed content (default: missing only)
crier audit --publish --yes --include-changed

# Filter by path
crier audit content/post --publish --yes --only-api

# Filter by date (relative)
crier audit --since 1w --publish --yes              # Last week
crier audit --since 1m --publish --yes              # Last month
crier audit --since 7d --until 1d --publish --yes   # 7 days ago to yesterday

# Filter by date (absolute)
crier audit --since 2025-12-01 --until 2025-12-31 --publish --yes

# Combine filters
crier audit content/post --since 1m --only-api --long-form --sample 10 --publish --yes
```

### Filter Reference

| Filter | Description |
|--------|-------------|
| `[PATH]` | Only scan specific directory |
| `--since` | Only content from this date (`1d`, `1w`, `1m`, `1y`, or `YYYY-MM-DD`) |
| `--until` | Only content until this date |
| `--only-api` | Skip manual/import/paste platforms |
| `--long-form` | Skip short-form platforms (bluesky, mastodon, twitter, threads) |
| `--sample N` | Random sample of N items |
| `--include-changed` | Also update changed content (default: missing only) |
| `--batch` | Non-interactive mode (implies `--yes --json`, skips manual platforms) |
| `--json` | Output results as JSON |

Filters are applied in order: path → date → platform mode → content type → changed → sampling

## Delete & Archive

### Deleting Content

Remove published content from platforms:

```bash
# Delete from specific platform
crier delete post.md --from devto

# Delete from all platforms
crier delete post.md --all

# Preview what would be deleted
crier delete post.md --all --dry-run
```

Deletion records are preserved in the registry (marked as deleted) to prevent accidental re-publishing.

### Archiving Content

Archive content to exclude it from `audit --publish`:

```bash
# Archive (exclude from bulk publishing)
crier archive post.md

# Unarchive (include again)
crier unarchive post.md

# Include archived in audit
crier audit --include-archived
```

## Scheduling

Schedule posts for future publication:

```bash
# Schedule a post
crier publish post.md --to devto --schedule "tomorrow 9am"
crier publish post.md --to bluesky --schedule "2025-02-01 14:00"

# View scheduled posts
crier schedule list

# Show details
crier schedule show abc123

# Cancel a scheduled post
crier schedule cancel abc123

# Publish all due posts
crier schedule run
```

Supports natural language times ("tomorrow", "next monday 9am") and ISO format.

## Analytics

Track engagement across platforms:

```bash
# Show stats for all content
crier stats

# Stats for specific file
crier stats post.md

# Top articles by engagement
crier stats --top 10

# Filter by date
crier stats --since 1m

# Refresh from platforms (ignore cache)
crier stats --refresh

# JSON output
crier stats --json
```

Stats are cached for 1 hour. Supported platforms: dev.to, Bluesky, Mastodon.

## Threading

Split long content into threads for social platforms:

```bash
# Auto-split into thread
crier publish post.md --to bluesky --thread

# Choose thread style
crier publish post.md --to mastodon --thread --thread-style numbered  # 1/5, 2/5...
crier publish post.md --to bluesky --thread --thread-style emoji      # 🧵 1/5...
crier publish post.md --to mastodon --thread --thread-style simple    # No prefix
```

Thread splitting priority:
1. Manual markers: `<!-- thread -->` in content
2. Paragraph boundaries (double newline)
3. Sentence boundaries (if paragraph too long)

Supported platforms: Bluesky, Mastodon.

## Pre-Publish Validation

Validate content before publishing with `crier check`:

```bash
# Check a single file
crier check post.md

# Check with platform context (validates platform-specific limits)
crier check post.md --to bluesky --to devto

# Check all content
crier check --all

# Strict mode: warnings become errors
crier check post.md --strict

# Check external links (opt-in, makes HTTP requests)
crier check post.md --check-links

# JSON output
crier check post.md --json
```

**Checks performed:**
| Check | Severity | Description |
|-------|----------|-------------|
| `missing-title` | error | No title in front matter |
| `empty-body` | error | No content body |
| `missing-date` | warning | No date field |
| `missing-tags` | warning | No tags defined |
| `title-length` | warning | Title exceeds recommended length |
| `short-body` | warning | Very short content body |
| `bluesky-length` | warning | Content exceeds Bluesky character limit |
| `mastodon-length` | warning | Content exceeds Mastodon character limit |
| `missing-description` | info | No description field |
| `devto-canonical` | info | No canonical URL for dev.to |

**Publish integration:** Pre-publish checks run automatically before publishing. Use `--no-check` to skip, `--strict` to block on warnings.

**Severity overrides** in `.crier/config.yaml`:
```yaml
checks:
  missing-tags: disabled    # Don't care about tags
  missing-date: error       # Promote to error
  short-body: disabled      # Allow short posts
```

## Quiet Mode

Suppress non-essential output for scripting:

```bash
crier publish post.md --to devto --quiet
crier audit --publish --yes --quiet
crier search --tag python --quiet
```

Quiet mode only shows errors and final results. Combine with `--json` for fully parseable output.

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success — all operations completed |
| `1` | Failure — operation failed or validation error |
| `2` | Partial — some operations succeeded, some failed |

```bash
# Check exit code in scripts
crier publish post.md --to devto --batch
if [ $? -eq 2 ]; then
  echo "Some platforms failed, retrying..."
fi
```

## Getting API Keys

### dev.to
1. Go to https://dev.to/settings/extensions
2. Generate API key

### Hashnode
1. Go to https://hashnode.com/settings/developer
2. Generate Personal Access Token

### Medium
1. Go to https://medium.com/me/settings/security
2. Generate Integration Token

### Bluesky
1. Go to Settings → App Passwords
2. Create an app password
3. Use format: `yourhandle.bsky.social:xxxx-xxxx-xxxx-xxxx`

### Mastodon
1. Go to Settings → Development → New Application
2. Create app with `write:statuses` scope
3. Use format: `instance.social:your-access-token`

### Twitter/X
Uses copy-paste mode - generates formatted tweet text for manual posting.
No API setup required. Just set any placeholder value:
```bash
crier config set twitter.api_key manual
```

### Ghost
1. Go to Settings → Integrations → Add custom integration
2. Copy the Admin API Key (format: `key_id:key_secret`)
3. Use format: `https://yourblog.com:key_id:key_secret`

### WordPress
**WordPress.com:**
1. Go to https://developer.wordpress.com/apps/
2. Create an app and get OAuth token
3. Use format: `yoursite.wordpress.com:access_token`

**Self-hosted WordPress:**
1. Go to Users → Profile → Application Passwords
2. Create a new application password
3. Use format: `https://yoursite.com:username:app_password`

### Buttondown
1. Go to https://buttondown.email/settings/programming
2. Copy your API key
3. Use format: `api_key`

### Threads
1. Create a Meta Developer account at https://developers.facebook.com/
2. Create an app with Threads API access
3. Get your user_id and access_token
4. Use format: `user_id:access_token`

### Telegram
1. Message @BotFather to create a bot and get the bot token
2. Add your bot as admin to your channel
3. Get your channel's chat_id (e.g., `@yourchannel` or numeric ID)
4. Use format: `bot_token:chat_id`

### Discord
1. Go to Server Settings → Integrations → Webhooks
2. Create a new webhook for your announcement channel
3. Copy the webhook URL
4. Use the full URL as the API key

## License

MIT
