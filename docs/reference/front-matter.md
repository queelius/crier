# Front Matter Reference

Crier reads YAML front matter from your markdown files.

## Basic Format

```markdown
---
title: "Your Post Title"
description: "A brief description for SEO and previews"
tags: [python, automation, cli]
canonical_url: https://yourblog.com/your-post
published: true
---

Your content here...
```

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | Yes* | Post title. Falls back to filename if not set. |
| `description` | string | No | Short description for SEO and social previews. |
| `tags` | list or string | No | Tags/hashtags. Can be YAML list or comma-separated. |
| `canonical_url` | string | No | URL of the original post (for cross-posts). |
| `published` | boolean | No | Whether to publish immediately (default: true). |

## Tags Format

Tags can be specified in multiple formats:

```yaml
# YAML list (recommended)
tags: [python, cli, automation]

# YAML list (multi-line)
tags:
  - python
  - cli
  - automation

# Comma-separated string
tags: python, cli, automation
```

## Platform-Specific Behavior

### Blog Platforms

- **Title**: Used as article title
- **Description**: Used as excerpt/subtitle
- **Tags**: Applied as platform tags (may be limited, e.g., dev.to max 4)
- **Canonical URL**: Set as canonical link
- **Body**: Published as full article

### Social Platforms

- **Title**: Included in post text
- **Description**: Included in post text (if space allows)
- **Tags**: Converted to hashtags
- **Canonical URL**: Appended as link
- **Body**: Not used (post is a link announcement)

### Example: Blog Post

```markdown
---
title: "Building a CLI Tool with Click"
description: "A practical guide to creating command-line interfaces in Python"
tags: [python, cli, click, tutorial]
canonical_url: https://myblog.com/click-cli-tutorial
published: true
---

# Introduction

Click is a Python package for creating beautiful command-line interfaces...
```

### Example: Announcement

For social platforms, only front matter matters:

```markdown
---
title: "New Blog Post: Building a CLI Tool with Click"
description: "Learn how to create professional CLIs in Python"
tags: [python, cli]
canonical_url: https://myblog.com/click-cli-tutorial
---

This body text is ignored for social platforms.
```

## Draft Mode

Set `published: false` or use `--draft` flag:

```yaml
---
title: "Work in Progress"
published: false
---
```

```bash
# Or via CLI
crier publish post.md --to devto --draft
```
