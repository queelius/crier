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
crier init                              # Interactive setup wizard
crier publish FILE --to PLATFORM        # Publish to platform(s)
crier publish FILE --to PLATFORM --manual  # Manual copy-paste mode
crier audit                             # See what's missing/changed
crier audit --publish                   # Bulk publish interactively
crier status [FILE]                     # Show publication status
crier list PLATFORM                     # List your articles
crier config show                       # Show configuration
crier config set KEY VALUE              # Set configuration
crier doctor                            # Verify API keys work
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
