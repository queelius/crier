# CLI Reference

Complete reference for all Crier commands.

## publish

Publish a markdown file to one or more platforms.

```bash
crier publish FILE [OPTIONS]
```

**Arguments:**

- `FILE` — Path to the markdown file to publish

**Options:**

| Option | Description |
|--------|-------------|
| `--to, -t PLATFORM` | Platform to publish to (can be repeated) |
| `--profile, -p NAME` | Use a predefined profile |
| `--draft` | Publish as draft |
| `--dry-run` | Preview without publishing |

**Examples:**

```bash
# Publish to a single platform
crier publish post.md --to devto

# Publish to multiple platforms
crier publish post.md --to devto --to bluesky --to mastodon

# Use a profile
crier publish post.md --profile blogs

# Combine profile and additional platforms
crier publish post.md --profile blogs --to telegram

# Preview what would be published
crier publish post.md --profile everything --dry-run

# Publish as draft
crier publish post.md --to devto --draft
```

---

## status

Show publication status for a file or all tracked posts.

```bash
crier status [FILE] [OPTIONS]
```

**Arguments:**

- `FILE` — (Optional) Path to a specific file

**Options:**

| Option | Description |
|--------|-------------|
| `--all, -a` | Show all tracked posts |

**Examples:**

```bash
# Status for a specific file
crier status my-post.md

# Status for all tracked posts
crier status --all
```

---

## audit

Audit content to see what's missing from platforms.

```bash
crier audit [PATH] [OPTIONS]
```

**Arguments:**

- `PATH` — File or directory to audit (default: current directory)

**Options:**

| Option | Description |
|--------|-------------|
| `--to, -t PLATFORM` | Only check specific platform(s) |
| `--profile, -p NAME` | Only check platforms in a profile |

**Examples:**

```bash
# Audit all markdown files in current directory
crier audit

# Audit a specific directory
crier audit ./posts

# Audit against specific platforms
crier audit ./posts --to devto --to hashnode

# Audit against a profile
crier audit ./posts --profile blogs
```

---

## backfill

Publish content that's missing from platforms.

```bash
crier backfill PATH [OPTIONS]
```

**Arguments:**

- `PATH` — File or directory to backfill

**Options:**

| Option | Description |
|--------|-------------|
| `--to, -t PLATFORM` | Only publish to specific platform(s) |
| `--profile, -p NAME` | Only publish to platforms in a profile |
| `--dry-run` | Preview without publishing |
| `--yes, -y` | Skip confirmation prompt |

**Examples:**

```bash
# Backfill a directory to all configured platforms
crier backfill ./posts

# Backfill to specific platforms
crier backfill ./posts --to bluesky

# Backfill using a profile
crier backfill ./posts --profile social

# Preview what would be published
crier backfill ./posts --dry-run

# Skip confirmation
crier backfill ./posts --yes
```

---

## update

Update an existing article on a platform.

```bash
crier update PLATFORM ARTICLE_ID --file FILE
```

**Arguments:**

- `PLATFORM` — Platform name (e.g., devto, hashnode)
- `ARTICLE_ID` — The article ID on the platform

**Options:**

| Option | Description |
|--------|-------------|
| `--file, -f FILE` | Markdown file with updated content (required) |

**Examples:**

```bash
crier update devto 12345 --file updated-post.md
```

---

## list

List your articles on a platform.

```bash
crier list PLATFORM [OPTIONS]
```

**Arguments:**

- `PLATFORM` — Platform name

**Options:**

| Option | Description |
|--------|-------------|
| `--limit, -n NUMBER` | Number of articles to show (default: 10) |

**Examples:**

```bash
crier list devto
crier list devto --limit 20
```

---

## doctor

Check configuration and validate API keys.

```bash
crier doctor
```

Validates all configured API keys by making test requests to each platform.

---

## platforms

List all available platforms and their configuration status.

```bash
crier platforms
```

---

## init-action

Set up GitHub Action workflow and secrets for auto-publishing.

```bash
crier init-action [OPTIONS]
```

Creates the workflow file and configures GitHub repository secrets from your local crier config.

**Options:**

| Option | Description |
|--------|-------------|
| `--content-path, -c PATH` | Custom path to content directory |
| `--dry-run` | Preview without making changes |
| `--yes, -y` | Skip confirmation prompts |

**Requirements:**

- GitHub CLI (`gh`) must be installed
- Must be authenticated: `gh auth login`
- Must be in a git repo with a GitHub remote

**Examples:**

```bash
# Standard setup (uses posts/ or content/)
crier init-action

# Preview what would be done
crier init-action --dry-run

# Custom content path
crier init-action --content-path blog/articles

# Non-interactive setup
crier init-action --yes
```

---

## config

Manage Crier configuration.

### config set

Set a configuration value.

```bash
crier config set KEY VALUE
```

**Examples:**

```bash
crier config set devto.api_key YOUR_KEY
crier config set bluesky.api_key "handle.bsky.social:app-password"
```

### config show

Show current configuration (API keys are masked).

```bash
crier config show
```

### config profile set

Create or update a publishing profile.

```bash
crier config profile set NAME PLATFORMS...
```

**Examples:**

```bash
# Create a profile
crier config profile set blogs devto hashnode ghost

# Profiles can reference other profiles
crier config profile set everything blogs social
```

### config profile show

Show profiles.

```bash
crier config profile show [NAME]
```

### config profile delete

Delete a profile.

```bash
crier config profile delete NAME
```
