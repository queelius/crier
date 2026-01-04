"""Claude Code skill installation for crier."""

from pathlib import Path

SKILL_NAME = "crier"

# Claude Code skills directory structure
GLOBAL_SKILLS_DIR = Path.home() / ".claude" / "skills"
LOCAL_SKILLS_DIR = Path(".claude") / "skills"

SKILL_CONTENT = '''\
---
name: crier
description: Cross-post blog content to social platforms. Claude handles audit, user selection, and generates rewrites for short-form platforms.
---

# Crier - Cross-Posting Tool

Crier cross-posts blog content from markdown files (with YAML front matter) to multiple platforms.

## Claude Code Workflow

When the user wants to cross-post content, follow this workflow:

### 1. Audit - See What Needs Publishing

Run `crier audit` to see status:
- `✓` = published and up-to-date
- `⚠` = published but content changed (needs update)
- `✗` = not published (missing)

```bash
crier audit                    # Uses configured content_paths
crier audit ./posts            # Specific directory
crier audit --to bluesky       # Check specific platform
```

### 2. Select - Let User Choose

Use AskUserQuestion to let user choose which items to publish/update.
Or use `crier audit --publish` for interactive checkbox selection.

```bash
# Interactive selection
crier audit --publish

# Publish all without prompting
crier audit --publish --yes
```

### 3. Publish - Handle Each Item

For each selected item:

**Long-form platforms** (devto, hashnode, ghost, wordpress, medium):
```bash
crier publish article.md --to devto
```

**Short-form platforms** (bluesky, mastodon, twitter, threads):
Generate a short announcement, then:
```bash
crier publish article.md --to bluesky \\
  --rewrite "Your announcement text" \\
  --rewrite-author "claude-code"
```

## Handling "Content Too Long" Errors

If you see: `Content too long for bluesky: 5000 characters (limit: 300)`

Generate a short announcement that:
1. Is under the platform's character limit
2. Mentions the article title/topic
3. Is engaging for the platform's audience
4. Does NOT include the URL (crier appends canonical_url automatically)

Then retry with `--rewrite`.

### Platform Character Limits
- Bluesky: 300 chars
- Twitter: 280 chars
- Mastodon: 500 chars
- Threads: 500 chars

## Platform Update Support

When content changes (⚠ dirty), `audit --publish` will update:
- **Supports update**: devto, hashnode, ghost, wordpress, buttondown, mastodon, telegram, discord
- **No update support**: bluesky, twitter, threads (will show error)

For platforms without update support, the user must decide whether to delete and re-post manually.

## Manual Mode

For platforms with restrictive API access (Medium, LinkedIn, Twitter/X), use `--manual`:

```bash
crier publish article.md --to medium --manual
crier publish article.md --to linkedin --manual
```

**Auto-manual mode**: Configure a platform with `api_key: manual` to always use copy-paste mode:

```bash
crier config set twitter.api_key manual
crier config set linkedin.api_key manual

# Now these automatically use manual mode
crier publish article.md --to twitter
```

Manual mode workflow:
1. Formats content for the platform
2. Copies to clipboard and opens browser
3. Asks user to confirm after posting
4. Records to registry only if confirmed

This is useful when API access is problematic or unavailable.

## Command Roles

**`audit`** = Status checking + bulk operations
- See what's missing/dirty across all content
- Bulk publish/update with `--publish`
- Preview with `--dry-run`

**`publish`** = Single-file with full control
- Direct publish one file
- `--rewrite` for short-form platforms
- `--dry-run` to preview
- `--draft` to publish as draft

## Commands Reference

```bash
# See what's missing or changed
crier audit
crier audit --to bluesky --to devto

# Preview what would be published (no changes)
crier audit --dry-run

# Bulk publish missing/update changed (interactive)
crier audit --publish

# Bulk publish all without prompting
crier audit --publish --yes

# Single file to one platform
crier publish article.md --to devto

# Single file with rewrite for short-form
crier publish article.md --to bluesky \\
  --rewrite "Announcement text" \\
  --rewrite-author "claude-code"

# Preview single file (no changes)
crier publish article.md --to devto --dry-run

# Check status of specific file
crier status article.md

# List what you've published to a platform
crier list devto

# Validate API keys work
crier doctor
```

## Configuration

```bash
# Set API key
crier config set <platform>.api_key <key>

# Create a profile (group of platforms)
crier config profile set social bluesky mastodon threads

# Add content path for scanning
crier config content add ./posts
```

## Front Matter Requirements

Articles need YAML front matter with:
```yaml
---
title: "Your Article Title"
canonical_url: "https://yourblog.com/your-article/"
---
```

The `canonical_url` is required for registry tracking and is appended to short-form posts.
'''


def get_skill_dir(local: bool = False) -> Path:
    """Get the skills directory path."""
    if local:
        return LOCAL_SKILLS_DIR / SKILL_NAME
    return GLOBAL_SKILLS_DIR / SKILL_NAME


def get_skill_path(local: bool = False) -> Path:
    """Get the SKILL.md file path."""
    return get_skill_dir(local) / "SKILL.md"


def is_installed(local: bool | None = None) -> dict[str, bool]:
    """Check if skill is installed.

    Args:
        local: If True, check only local. If False, check only global.
               If None, check both.

    Returns:
        Dict with 'global' and 'local' keys indicating installation status.
    """
    result = {"global": False, "local": False}

    if local is None or local is False:
        result["global"] = get_skill_path(local=False).exists()

    if local is None or local is True:
        result["local"] = get_skill_path(local=True).exists()

    return result


def install(local: bool = False) -> Path:
    """Install the crier skill.

    Args:
        local: If True, install to .claude/skills/ (repo-local).
               If False, install to ~/.claude/skills/ (global).

    Returns:
        Path to the installed SKILL.md file.
    """
    skill_dir = get_skill_dir(local)
    skill_path = get_skill_path(local)

    # Create directory
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Write skill file
    skill_path.write_text(SKILL_CONTENT)

    return skill_path


def uninstall(local: bool = False) -> bool:
    """Uninstall the crier skill.

    Args:
        local: If True, uninstall from .claude/skills/.
               If False, uninstall from ~/.claude/skills/.

    Returns:
        True if skill was removed, False if it wasn't installed.
    """
    skill_path = get_skill_path(local)
    skill_dir = get_skill_dir(local)

    if not skill_path.exists():
        return False

    # Remove the skill file
    skill_path.unlink()

    # Remove the directory if empty
    try:
        skill_dir.rmdir()
    except OSError:
        pass  # Directory not empty or other error

    return True


def get_skill_content() -> str:
    """Get the skill content."""
    return SKILL_CONTENT
