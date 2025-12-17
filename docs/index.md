# Crier

**Cross-post your content everywhere.**

Crier is a CLI tool that publishes your markdown content to multiple platforms with a single command. Like a town crier announcing your content to the world.

## Why Crier?

Content creators face a fragmented distribution landscape. You write a blog post, then must manually:

- Publish to your blog
- Cross-post to dev.to, Hashnode, Medium for discovery
- Announce on Bluesky, Mastodon, Twitter for reach
- Send to newsletter subscribers
- Post to Discord/Telegram communities

Crier automates this. **Write once, publish everywhere.**

## Philosophy

- **Write Once, Publish Everywhere** — Your markdown file is the source of truth
- **Unix Philosophy** — Small tool, one job, composes well with other tools
- **Developer-First** — Markdown + YAML front matter, CLI-only, no GUI
- **Platform Agnostic** — Easy to add new platforms

## Quick Example

```bash
# Configure platforms
crier config set devto.api_key YOUR_KEY
crier config set bluesky.api_key "handle.bsky.social:app-password"

# Create a profile for blog platforms
crier config profile set blogs devto hashnode ghost

# Publish to all blog platforms
crier publish my-post.md --profile blogs

# See what's missing
crier audit ./posts --profile blogs

# Backfill missing publications
crier backfill ./posts --profile blogs
```

## Supported Platforms

| Category | Platforms |
|----------|-----------|
| **Blog** | dev.to, Hashnode, Medium, Ghost, WordPress |
| **Newsletter** | Buttondown |
| **Social** | Bluesky, Mastodon, LinkedIn, Threads, Twitter |
| **Announcement** | Telegram, Discord |

## Installation

```bash
pip install crier
```

## Next Steps

- [Getting Started](getting-started.md) — Install and publish your first post
- [Configuration](guides/configuration.md) — Set up API keys and profiles
- [CLI Reference](reference/cli.md) — All commands and options
