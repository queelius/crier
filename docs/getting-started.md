# Getting Started

This guide walks you through installing Crier and publishing your first post.

## Installation

```bash
pip install crier
```

## Configure Your First Platform

Let's start with dev.to, which has a simple API key setup:

1. Go to [dev.to/settings/extensions](https://dev.to/settings/extensions)
2. Generate an API key
3. Configure Crier:

```bash
crier config set devto.api_key YOUR_API_KEY
```

Verify it works:

```bash
crier doctor
```

You should see dev.to listed as "Healthy".

## Create a Markdown Post

Create a file called `my-first-post.md`:

```markdown
---
title: "My First Cross-Posted Article"
description: "Testing out Crier for cross-posting"
tags: [testing, crier, automation]
canonical_url: https://myblog.com/my-first-post
published: true
---

This is my first post published with Crier!

## Why Crier?

Because manually posting to multiple platforms is tedious.
```

## Preview Before Publishing

Use `--dry-run` to see what would be published:

```bash
crier publish my-first-post.md --dry-run
```

## Publish

When you're ready:

```bash
crier publish my-first-post.md --to devto
```

## Check Publication Status

```bash
crier status my-first-post.md
```

## Add More Platforms

Configure additional platforms:

```bash
# Bluesky
crier config set bluesky.api_key "handle.bsky.social:app-password"

# Mastodon
crier config set mastodon.api_key "mastodon.social:access-token"

# Hashnode
crier config set hashnode.api_key "your-token"
```

See [Platforms](platforms/index.md) for setup instructions for each platform.

## Create Publishing Profiles

Group platforms for convenience:

```bash
# Create profiles
crier config profile set blogs devto hashnode
crier config profile set social bluesky mastodon

# Publish to a profile
crier publish my-post.md --profile blogs
```

## Next Steps

- [Configuration Guide](guides/configuration.md) — Detailed configuration options
- [Publication Tracking](guides/tracking.md) — Track what's published where
- [Backfill Guide](guides/backfill.md) — Publish old content to new platforms
