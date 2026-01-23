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
| linkedin  | API    | 3000   | No       | Long-form but has limit        |
| medium    | import | ∞      | No       | User imports from canonical URL |
| twitter   | paste  | 280    | No       | Short-form, copy-paste         |
| threads   | paste  | 500    | No       | Short-form, copy-paste         |

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

[runs: crier publish article.md --to bluesky \
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

## Interpreting Audit Scope

The `crier audit` command scans all directories in `content_paths` by default. Users often want to scope to specific content types.

**Reading user intent:**

| User says... | Likely scope |
|--------------|--------------|
| "last month of content", "recent content", "what needs posting" | All content (`crier audit --since 1m`) |
| "blog posts", "posts", "articles" | `crier audit content/post` |
| "projects" | `crier audit content/projects` |
| "papers", "research" | `crier audit content/papers` |

**When uncertain:**
- Run `crier config show` to see configured content paths (crier finds its config automatically, like git)
- Look at what subdirectories exist under the content paths
- Make a reasonable choice based on available clues
- If wrong, the user will clarify - that's what conversation is for

**Don't overthink it.** A site might have `content/post`, `content/projects`, `content/papers`, `content/writing`, etc. User language usually provides enough signal. When it doesn't, just pick a reasonable default and let the user correct you.

## Key Commands

```bash
# Check what needs publishing
crier audit
crier audit content/post/my-article/index.md

# Publish to API platform
crier publish article.md --to devto

# Publish with rewrite for short-form
crier publish article.md --to bluesky \
  --rewrite "Short announcement text" \
  --rewrite-author "claude-code"

# Auto-rewrite using configured LLM (requires LLM config)
crier publish article.md --to bluesky --auto-rewrite

# Import/paste mode (skips interactive prompts)
crier publish article.md --to medium --yes
crier publish article.md --to twitter --yes

# Check API keys
crier doctor

# Manual registry management
crier register <file> --platform <platform> [--url <url>]
crier unregister <file> --platform <platform>
```

## Automation Modes

### Batch Mode

Use `--batch` for fully automated, non-interactive publishing:

```bash
# Batch mode: implies --yes --json, skips manual/import platforms
crier publish article.md --to devto --to bluesky --batch
crier audit --publish --batch
```

Batch mode:
- Implies `--yes` (no prompts)
- Implies `--json` (structured output)
- Skips manual/import platforms automatically
- Perfect for CI/CD and automated workflows

### JSON Output

Use `--json` for machine-readable output:

```bash
# JSON output for publish
crier publish article.md --to devto --json

# JSON output for audit
crier audit --json
```

JSON output structure:
```json
{
  "command": "publish",
  "file": "article.md",
  "results": [
    {"platform": "devto", "success": true, "url": "https://..."}
  ],
  "summary": {"succeeded": 1, "failed": 0, "skipped": 0}
}
```

### Auto-Rewrite with LLM

Use `--auto-rewrite` to automatically generate short-form content:

```bash
# Basic auto-rewrite
crier publish article.md --to bluesky --auto-rewrite

# Preview with dry-run (shows char budget like "285/300 chars, 95%")
crier publish article.md --to bluesky --auto-rewrite --dry-run

# Retry up to 3 times if output exceeds character limit
crier publish article.md --to bluesky --auto-rewrite -R 3

# Truncate at sentence boundary if retries fail
crier publish article.md --to bluesky --auto-rewrite -R 3 --auto-rewrite-truncate

# Override temperature (0.0-2.0, higher=more creative)
crier publish article.md --to bluesky --auto-rewrite --temperature 1.2

# Override model
crier publish article.md --to bluesky --auto-rewrite --model gpt-4o
```

**Simplest setup:** If `OPENAI_API_KEY` is set, it just works (defaults to gpt-4o-mini).

**Or configure in `~/.config/crier/config.yaml`:**
```yaml
# Minimal (defaults to OpenAI + gpt-4o-mini)
llm:
  api_key: sk-...

# For Ollama/other providers
llm:
  base_url: http://localhost:11434/v1
  model: llama3
```

## Bulk Operations

For large content libraries, use filters to control scope:

```bash
# Batch mode: publish to API long-form platforms (fully automated)
crier audit --publish --batch --long-form

# Post 5 random articles to blog platforms
crier audit --publish --yes --only-api --long-form --sample 5

# All missing to API platforms (skips manual/import)
crier audit --publish --yes --only-api

# Include updates to changed content
crier audit --publish --yes --include-changed

# Filter by path - only posts (not projects, papers, etc.)
crier audit content/post --publish --yes --only-api --long-form --sample 5

# Only projects
crier audit content/projects --only-api

# Posts from last week
crier audit --since 1w --publish --yes --only-api

# Posts from December 2025
crier audit --since 2025-12-01 --until 2025-12-31 --publish --yes

# Sample 5 recent posts (last month)
crier audit --sample 5 --since 1m --only-api --long-form
```

### Filters
- `[PATH]` - Limit to specific directory (e.g., `content/post`, `content/projects`)
- `--since` - Only content from this date (e.g., `1d`, `1w`, `1m`, `2025-01-01`)
- `--until` - Only content until this date
- `--only-api` - Skip manual/import/paste platforms
- `--long-form` - Skip short-form platforms (bluesky, mastodon, twitter, threads)
- `--sample N` - Random sample of N items
- `--include-changed` - Also update changed content (default: missing only)
- `--batch` - Non-interactive mode (implies --yes --json --only-api)
- `--json` - Output results as JSON

### Claude Code Bulk Workflow

1. Run automated batch: `crier audit --publish --batch --long-form --sample 10`
2. Check what else needs work: `crier audit`
3. Handle short-form platforms with --rewrite or --auto-rewrite
4. Guide user through manual/import platforms

## Important Rules

1. **Crier appends the canonical URL** to short-form posts automatically. Don't include it in your rewrite text.

2. **DevTo tags are auto-sanitized**. Hyphens removed, lowercase, max 4 tags. No action needed.

3. **Use --yes for non-API modes**. This skips interactive prompts that don't work through Claude Code.

4. **Ask simple yes/no** after manual operations. Trust the user's answer.

5. **Show the canonical URL** for import-mode platforms. It's the key piece of information.

6. **Use --batch for automation**. It handles all the flags for non-interactive use.

7. **Relative links are auto-resolved**. Links like `/posts/other/` are converted to absolute URLs using `site_base_url`. No manual URL fixing needed.

## Configuration

### Global Config (~/.config/crier/config.yaml)
API keys and profiles (shared across all projects):

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

LLM configuration (for --auto-rewrite):
```yaml
# If OPENAI_API_KEY env var is set, no config needed!
# Otherwise, minimal config:
llm:
  api_key: sk-...  # defaults to OpenAI + gpt-4o-mini

# Or for Ollama:
llm:
  base_url: http://localhost:11434/v1
  model: llama3

# Full config with retry and truncation defaults:
llm:
  api_key: sk-...
  base_url: https://api.openai.com/v1
  model: gpt-4o-mini
  temperature: 0.7          # 0.0-2.0, higher=more creative
  retry_count: 0            # Auto-retry if output exceeds limit
  truncate_fallback: false  # Hard-truncate if retries fail
```

Set LLM config via CLI:
```bash
crier config llm set temperature 0.9
crier config llm set retry_count 3
crier config llm set truncate_fallback true
```

### Local Config (.crier/config.yaml)
Project-specific settings:

```yaml
# Content discovery
content_paths:
  - content
site_base_url: https://yoursite.com
exclude_patterns:
  - _index.md           # Hugo section pages
file_extensions:
  - .md
  - .mdx                # Optional: for MDX content

# Defaults
default_profile: everything   # Used when no --to or --profile specified
rewrite_author: claude-code   # Default author for Claude-generated rewrites
```

| Option | Purpose |
|--------|---------|
| `content_paths` | Directories to scan for content |
| `site_base_url` | For inferring canonical URLs |
| `exclude_patterns` | Files to skip (e.g., `_index.md`) |
| `file_extensions` | Extensions to scan (default: `.md`) |
| `default_profile` | Profile to use when none specified |
| `rewrite_author` | Default `--rewrite-author` value |

## Front Matter Requirements

```yaml
---
title: "Your Article Title"
canonical_url: "https://yourblog.com/your-article/"
---
```

The `canonical_url` is required - it's the article's identity for tracking and linking.
