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

# Crier Cross-Posting Workflow

Crier cross-posts blog content to multiple platforms. The blog is the canonical source of truth.

**Division of labor:**
- **Crier** does mechanics: API calls, registry tracking, clipboard, browser
- **Claude** does judgment: summaries, error handling, user interaction

## Platform Reference

| Platform  | Mode   | Limit  | Updates? | Notes                          |
|-----------|--------|--------|----------|--------------------------------|
| devto     | API    | ∞      | Yes      | Tags auto-sanitized (no hyphens) |
| hashnode  | API    | ∞      | Yes      |                                |
| bluesky   | API    | 300    | No       | Short-form, needs rewrite      |
| mastodon  | API    | 500    | Yes      | Short-form, needs rewrite      |
| medium    | import | ∞      | No       | User imports from canonical URL |
| twitter   | paste  | 280    | No       | Short-form, copy-paste         |
| threads   | paste  | 500    | No       | Short-form, copy-paste         |
| linkedin  | paste  | ∞      | No       | Copy-paste                     |

**Modes:**
- `API` = automatic posting via API
- `import` = user imports from canonical URL (like Medium)
- `paste` = user copy-pastes (content goes to clipboard)

## Complete Dialogue Examples

### Example 1: Cross-post a new article

```
User: cross-post my new blog post to the usual platforms

Claude: I'll cross-post content/post/2026-01-04-my-article/index.md

Let me check what's needed:
[runs: crier audit content/post/2026-01-04-my-article/index.md]

Platforms to post:
• devto (API) - will auto-post
• hashnode (API) - will auto-post
• bluesky (API, 300 chars) - I'll write a summary
• mastodon (API, 500 chars) - I'll write a summary
• medium (import) - you'll import from your URL

Proceed?

User: yes

Claude: [runs API posts for devto, hashnode]
[generates summaries and posts to bluesky, mastodon with --rewrite]

✓ devto: https://dev.to/user/my-article-abc
✓ hashnode: https://user.hashnode.dev/my-article
✓ bluesky: posted announcement
✓ mastodon: posted announcement

For Medium, import from your canonical URL:
https://yourblog.com/post/2026-01-04-my-article/

Go to: https://medium.com/p/import

[runs: crier publish article.md --to medium --yes]

Did you import to Medium successfully?

User: yes

Claude: ✓ All platforms complete.
```

### Example 2: Handling short-form platforms

```
User: post this to bluesky

Claude: [runs: crier publish article.md --to bluesky]

Error: Content too long for bluesky: 5000 characters (limit: 300)

I'll write a short announcement:

"New post: Exploring the mathematics of uncertainty - how
probabilistic thinking can transform how we approach
complex problems."

(198 chars + URL = within limit)

[runs: crier publish article.md --to bluesky \\
  --rewrite "New post: Exploring..." --rewrite-author "claude-code"]

✓ bluesky: https://bsky.app/profile/user/post/abc123
```

### Example 3: Import mode (Medium)

```
User: post to medium

Claude: Medium uses URL import. I'll set this up:

[runs: crier publish article.md --to medium --yes]

Import your article from this URL:
https://yourblog.com/post/2026-01-04-my-article/

Go to: https://medium.com/p/import

Did the import work?

User: yes

Claude: ✓ Registered in crier. Done!
```

### Example 4: Manual paste mode (Twitter)

```
User: share on twitter

Claude: Twitter uses copy-paste mode.

[runs: crier publish article.md --to twitter --yes]

I've copied this to your clipboard:
"New post: My Article Title - exploring key concepts...

https://yourblog.com/post/my-article/"

Go to: https://twitter.com/compose/tweet

Did you post it?

User: yes

Claude: ✓ Registered. All done!
```

## Workflow Decision Tree

### User wants to cross-post

1. **Audit first**: `crier audit <file>` or `crier audit` for all content
2. **Show platforms**: List what will happen for each platform
3. **Get confirmation**: Simple "Proceed?" - trust the user
4. **Execute by type**:
   - API long-form → `crier publish <file> --to <platform>`
   - API short-form → Generate summary, use `--rewrite`
   - Import mode → `crier publish ... --to medium --yes`, tell user to import
   - Paste mode → `crier publish ... --to twitter --yes`, tell user to paste
5. **Report results**: Show all successes, ask about manual platforms

### User says something changed

1. Run `crier audit` to see `⚠` dirty markers
2. For platforms that support update: re-run publish (auto-updates)
3. For platforms without update (bluesky, twitter): tell user they must delete/repost manually

### Failure handling

- Continue through all platforms even if some fail
- Report all failures at the end
- Don't ask user to retry - just report what happened

## Key Commands

```bash
# Check what needs publishing
crier audit
crier audit content/post/my-article/index.md

# Publish to API platform
crier publish article.md --to devto

# Publish with rewrite for short-form
crier publish article.md --to bluesky \\
  --rewrite "Short announcement text" \\
  --rewrite-author "claude-code"

# Import/paste mode (skips interactive prompts)
crier publish article.md --to medium --yes
crier publish article.md --to twitter --yes

# Check API keys
crier doctor

# Manual registry management
crier register <file> --platform <platform> [--url <url>]
crier unregister <file> --platform <platform>
```

## Bulk Operations

For large content libraries, use filters to control scope:

```bash
# Post 5 random articles to blog platforms (fully automated)
crier audit --publish --yes --only-api --long-form --sample 5

# All missing to API platforms (skips manual/import)
crier audit --publish --yes --only-api

# Include updates to changed content
crier audit --publish --yes --include-changed
```

### Filters
- `--only-api` - Skip manual/import/paste platforms
- `--long-form` - Skip short-form platforms (bluesky, mastodon, twitter, threads)
- `--sample N` - Random sample of N items
- `--include-changed` - Also update changed content (default: missing only)

### Claude Code Bulk Workflow

1. Run automated batch: `crier audit --publish --yes --only-api --long-form --sample 10`
2. Check what else needs work: `crier audit`
3. Handle short-form platforms with --rewrite
4. Guide user through manual/import platforms

## Important Rules

1. **Crier appends the canonical URL** to short-form posts automatically. Don't include it in your rewrite text.

2. **DevTo tags are auto-sanitized**. Hyphens removed, lowercase, max 4 tags. No action needed.

3. **Use --yes for non-API modes**. This skips interactive prompts that don't work through Claude Code.

4. **Ask simple yes/no** after manual operations. Trust the user's answer.

5. **Show the canonical URL** for import-mode platforms. It's the key piece of information.

## Configuration

```bash
# Set API key for automatic posting
crier config set devto.api_key <key>

# Set import mode (Medium)
crier config set medium.api_key import

# Set paste mode (Twitter)
crier config set twitter.api_key manual

# Check configuration
crier doctor
```

## Front Matter Requirements

```yaml
---
title: "Your Article Title"
canonical_url: "https://yourblog.com/your-article/"
---
```

The `canonical_url` is required - it's the article's identity for tracking and linking.
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
