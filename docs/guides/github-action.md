# GitHub Action Integration

Auto-publish content when you push to your repository.

## How It Works

1. You push a new/updated markdown file to `posts/`
2. GitHub Action triggers
3. Crier checks what's missing from your configured platforms
4. Crier publishes missing content
5. The publication registry is committed back to your repo

## Quick Setup (Recommended)

The easiest way to set up GitHub Actions is with the `init-action` command:

```bash
# In your content repository:
cd ~/repos/my-blog

# Set up workflow and secrets automatically
crier init-action
```

This command will:
1. Create `.github/workflows/crier-publish.yml` in your repo
2. Set all your configured API keys as GitHub repository secrets

**Options:**

```bash
# Preview what would be done
crier init-action --dry-run

# Specify a custom content path
crier init-action --content-path blog/articles

# Skip confirmation prompts
crier init-action --yes
```

**Requirements:**
- GitHub CLI (`gh`) must be installed and authenticated
- Run `gh auth login` if not already authenticated

## Manual Setup

If you prefer to set things up manually:

### 1. Add Secrets to Your Repository

Go to your repository's **Settings → Secrets and variables → Actions** and add:

| Secret Name | Value |
|------------|-------|
| `CRIER_DEVTO_API_KEY` | Your dev.to API key |
| `CRIER_BLUESKY_API_KEY` | `handle.bsky.social:app-password` |
| `CRIER_MASTODON_API_KEY` | `instance.social:access-token` |
| `CRIER_HASHNODE_API_KEY` | Your Hashnode token |

Only add secrets for platforms you want to use.

### 2. Create the Workflow File

Create `.github/workflows/crier-publish.yml` in your repository:

```yaml
name: Auto-Publish Content

on:
  push:
    branches: [main]
    paths:
      - 'posts/**/*.md'
  workflow_dispatch:

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install Crier
        run: pip install crier

      - name: Publish new content
        env:
          CRIER_DEVTO_API_KEY: ${{ secrets.CRIER_DEVTO_API_KEY }}
          CRIER_BLUESKY_API_KEY: ${{ secrets.CRIER_BLUESKY_API_KEY }}
          CRIER_MASTODON_API_KEY: ${{ secrets.CRIER_MASTODON_API_KEY }}
          CRIER_HASHNODE_API_KEY: ${{ secrets.CRIER_HASHNODE_API_KEY }}
        run: |
          echo "=== Configured Platforms ==="
          crier platforms

          echo "=== Audit ==="
          crier audit ./posts || true

          echo "=== Publishing ==="
          crier backfill ./posts --yes || true

      - name: Commit registry
        run: |
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git config user.name "github-actions[bot]"

          if [ -d ".crier" ]; then
            git add .crier/
            git diff --staged --quiet || git commit -m "Update publication registry"
            git push
          fi
```

### 3. Customize for Your Repository

**Change the posts path** if your content is elsewhere:

```yaml
paths:
  - 'content/**/*.md'  # or wherever your posts are
```

**Add a profile** for specific platforms:

First, create a crier config file in your repo at `.crier/config.yaml`:

```yaml
profiles:
  blogs: [devto, hashnode]
  social: [bluesky, mastodon]
  all: [blogs, social]
```

Then update the workflow:

```yaml
- name: Publish new content
  env:
    # ... secrets ...
  run: |
    crier backfill ./posts --profile blogs --yes
```

## Example: metafunctor Repository

For your metafunctor repo, create `.github/workflows/crier-publish.yml`:

```yaml
name: Cross-Post Content

on:
  push:
    branches: [main]
    paths:
      - 'posts/**/*.md'
  workflow_dispatch:

jobs:
  crosspost:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - run: pip install crier

      - name: Cross-post to platforms
        env:
          CRIER_DEVTO_API_KEY: ${{ secrets.CRIER_DEVTO_API_KEY }}
          CRIER_BLUESKY_API_KEY: ${{ secrets.CRIER_BLUESKY_API_KEY }}
        run: |
          crier audit ./posts
          crier backfill ./posts --yes

      - name: Save publication state
        run: |
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git config user.name "github-actions[bot]"
          git add .crier/ 2>/dev/null || true
          git diff --staged --quiet || git commit -m "📢 Update publication registry"
          git push
```

## How the Registry Works

The registry (`.crier/registry.yaml`) tracks what's been published:

```yaml
posts:
  "posts/my-article.md":
    title: "My Article"
    publications:
      devto:
        id: "12345"
        url: https://dev.to/user/my-article
        published_at: 2025-01-15T10:00:00Z
      bluesky:
        id: "abc123"
        published_at: 2025-01-15T10:05:00Z
```

When the action runs:
- `crier backfill` checks the registry
- Only publishes to platforms where the post is **not** already recorded
- Updates the registry after successful publications
- Commits the registry back to your repo

This means:
- A new post gets published to all platforms
- An existing post is skipped (already in registry)
- If you add a new platform, old posts get backfilled

## Manual Trigger

You can manually trigger the workflow from GitHub:

1. Go to **Actions** tab in your repository
2. Select the "Cross-Post Content" workflow
3. Click **Run workflow**

This is useful for:
- Initial backfill of existing content
- Retrying failed publications
- Testing your setup
