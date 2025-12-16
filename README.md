# Crier

Cross-post your content to dev.to, Hashnode, Medium, Bluesky, Mastodon, and more.

Like a town crier announcing your content to the world.

## Installation

```bash
pip install crier

# With Twitter/X support
pip install crier[twitter]

# All optional dependencies
pip install crier[all]
```

## Quick Start

```bash
# Configure your API keys
crier config set devto.api_key YOUR_API_KEY
crier config set bluesky.api_key "handle.bsky.social:app-password"
crier config set mastodon.api_key "mastodon.social:access-token"

# Publish a markdown file
crier publish post.md --to devto

# Publish to multiple platforms at once
crier publish post.md --to devto --to bluesky --to mastodon

# List your articles
crier list devto

# Update an existing article
crier update devto 12345 --file updated-post.md
```

## Supported Platforms

| Platform | API Key Format | Notes |
|----------|---------------|-------|
| **dev.to** | `api_key` | Full article support |
| **Hashnode** | `token` or `token:publication_id` | Full article support |
| **Medium** | `integration_token` | Publish only (no edit/list) |
| **Bluesky** | `handle:app_password` | Short posts with link cards |
| **Mastodon** | `instance:access_token` | Toots with hashtags |
| **LinkedIn** | `access_token` | Requires API access |
| **Twitter/X** | `key:secret:token:token_secret` | Requires Elevated access |

### Platform Notes

**Blog Platforms** (dev.to, Hashnode, Medium):
- Full markdown article publishing
- Preserves front matter (title, description, tags, canonical_url)
- Best for long-form content

**Social Platforms** (Bluesky, Mastodon, LinkedIn, Twitter):
- Creates short posts with link to canonical URL
- Uses title + description + hashtags from tags
- Best for announcing new content

## Configuration

API keys can be set via:

1. **Config file** (`~/.config/crier/config.yaml`):
   ```yaml
   platforms:
     devto:
       api_key: your_key_here
     bluesky:
       api_key: "handle.bsky.social:app-password"
     mastodon:
       api_key: "mastodon.social:access-token"
   ```

2. **Environment variables**:
   ```bash
   export CRIER_DEVTO_API_KEY=your_key_here
   export CRIER_BLUESKY_API_KEY="handle.bsky.social:app-password"
   ```

## Markdown Format

Crier reads standard markdown with YAML front matter:

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

## Commands

```bash
crier publish FILE [--to PLATFORM]...  # Publish to platform(s)
crier update PLATFORM ID --file FILE   # Update existing article
crier list PLATFORM                     # List your articles
crier config set KEY VALUE              # Set configuration
crier config show                       # Show configuration
crier platforms                         # List available platforms
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
Requires Twitter Developer account with Elevated access (complex setup).
Consider using Bluesky or Mastodon instead.

## License

MIT
