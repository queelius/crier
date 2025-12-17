# Publication Tracking

Crier tracks what content has been published where, enabling you to:

- See publication status at a glance
- Detect content changes since last publish
- Identify what's missing from platforms
- Backfill old content to new platforms

## The Registry

Publications are tracked in `.crier/registry.yaml` in your project directory.

```yaml
version: 1
posts:
  "posts/my-article.md":
    title: "My Article"
    checksum: "a1b2c3d4"
    canonical_url: https://myblog.com/my-article
    publications:
      devto:
        id: "12345"
        url: https://dev.to/user/my-article
        published_at: 2025-01-15T10:00:00Z
      bluesky:
        id: "bsky123"
        url: https://bsky.app/profile/user/post/bsky123
        published_at: 2025-01-15T10:05:00Z
```

## Checking Status

### Single File

```bash
crier status my-post.md
```

Shows:
- Where the file is published
- Publication dates
- Whether content has changed since publishing

### All Tracked Posts

```bash
crier status --all
```

Lists all posts in the registry with their publication platforms.

## Automatic Tracking

When you publish with Crier, successful publications are automatically recorded:

```bash
crier publish my-post.md --to devto --to bluesky
# Registry is updated automatically
```

## Content Change Detection

Crier stores a checksum of each file. If you edit a file after publishing, `crier status` will show it has changed:

```
⚠ Content has changed since last publication
```

This helps you know which posts need updating on platforms.

## Registry Location

The registry is created in `.crier/registry.yaml` relative to your current directory. You can:

- **Commit it**: Track publication history in version control
- **Gitignore it**: Keep it local only

```gitignore
# .gitignore - if you don't want to track publication history
.crier/
```
