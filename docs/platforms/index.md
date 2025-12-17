# Platforms Overview

Crier supports 13 platforms across four categories.

## Platform Categories

### Blog Platforms

Full markdown article publishing with metadata support.

| Platform | API Key Format | Features |
|----------|---------------|----------|
| [dev.to](devto.md) | `api_key` | Full CRUD, tags, canonical URL |
| [Hashnode](hashnode.md) | `token` or `token:publication_id` | Full CRUD, tags |
| [Medium](medium.md) | `integration_token` | Publish only |
| [Ghost](ghost.md) | `https://site:key_id:key_secret` | Full CRUD, self-hosted |
| [WordPress](wordpress.md) | `site:token` or `https://site:user:pass` | Full CRUD |

### Newsletter Platforms

Publish to email subscribers.

| Platform | API Key Format | Features |
|----------|---------------|----------|
| [Buttondown](buttondown.md) | `api_key` | Full CRUD |

### Social Platforms

Short posts with link cards for announcing content.

| Platform | API Key Format | Features |
|----------|---------------|----------|
| [Bluesky](bluesky.md) | `handle:app_password` | Posts with link cards |
| [Mastodon](mastodon.md) | `instance:access_token` | Toots with hashtags |
| [Threads](threads.md) | `user_id:access_token` | Posts (no edit) |
| [LinkedIn](linkedin.md) | `access_token` | Posts |
| [Twitter](twitter.md) | `any` (copy-paste mode) | Generates tweet text |

### Announcement Channels

Post to community channels/servers.

| Platform | API Key Format | Features |
|----------|---------------|----------|
| [Telegram](telegram.md) | `bot_token:chat_id` | Channel posts |
| [Discord](discord.md) | `webhook_url` | Webhook embeds |

## Platform Capabilities

| Platform | Publish | Update | List | Delete |
|----------|:-------:|:------:|:----:|:------:|
| dev.to | ✓ | ✓ | ✓ | ✓ |
| Hashnode | ✓ | ✓ | ✓ | ✓ |
| Medium | ✓ | ✗ | ✗ | ✗ |
| Ghost | ✓ | ✓ | ✓ | ✓ |
| WordPress | ✓ | ✓ | ✓ | ✓ |
| Buttondown | ✓ | ✓ | ✓ | ✓ |
| Bluesky | ✓ | ✗ | ✓ | ✓ |
| Mastodon | ✓ | ✗ | ✓ | ✓ |
| Threads | ✓ | ✗ | ✓ | ✗ |
| LinkedIn | ✓ | ✗ | ✗ | ✗ |
| Twitter | ✓* | ✓* | ✗ | ✗ |
| Telegram | ✓ | ✓ | ✗ | ✓ |
| Discord | ✓ | ✓ | ✗ | ✓ |

*Twitter uses copy-paste mode — generates formatted text for manual posting.

## Quick Setup

```bash
# Validate which platforms are configured
crier doctor

# List all platforms
crier platforms
```
