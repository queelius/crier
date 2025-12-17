# Backfill & Audit

Backfill lets you publish old content to platforms you've added later. Audit shows you what's missing.

## The Problem

You have existing blog posts that weren't published to all platforms:

- You wrote posts before using Crier
- You added a new platform (e.g., Bluesky)
- Some publications failed and you didn't retry

## Audit: See What's Missing

The `audit` command scans your content and shows what's missing where.

### Audit a Directory

```bash
crier audit ./posts
```

Output:
```
Content Audit
Checking 5 file(s) against 4 platform(s)

                    Audit Results
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━┓
│ File                 │ devto  │ bluesky │ mastodon │
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━┩
│ intro-to-python.md   │   ✓    │    ✓    │    ✓     │
│ advanced-typing.md   │   ✓    │    ✗    │    ✗     │
│ cli-design.md        │   ✓    │    ✗    │    ✓     │
│ old-post-2023.md     │   ✗    │    ✗    │    ✗     │
│ recent-thoughts.md   │   ✗    │    ✗    │    ✗     │
└──────────────────────┴────────┴─────────┴──────────┘

Summary:
  Files: 5
  Platforms checked: 4
  Published: 6
  Missing: 9
```

### Audit Against Specific Platforms

```bash
# Check only certain platforms
crier audit ./posts --to devto --to bluesky

# Check against a profile
crier audit ./posts --profile social
```

## Backfill: Publish Missing Content

The `backfill` command publishes content that's missing from platforms.

### Preview First

Always preview before publishing:

```bash
crier backfill ./posts --dry-run
```

### Backfill Everything

```bash
crier backfill ./posts
```

You'll be prompted to confirm before publishing.

### Backfill to Specific Platforms

```bash
# Only backfill to Bluesky
crier backfill ./posts --to bluesky

# Only backfill to a profile
crier backfill ./posts --profile social
```

### Skip Confirmation

```bash
crier backfill ./posts --yes
```

### Backfill a Single File

```bash
crier backfill my-old-post.md
```

## Typical Workflow

1. **Audit** to see the current state:
   ```bash
   crier audit ./posts --profile everything
   ```

2. **Dry run** to preview what would happen:
   ```bash
   crier backfill ./posts --profile everything --dry-run
   ```

3. **Backfill** to publish missing content:
   ```bash
   crier backfill ./posts --profile everything
   ```

4. **Verify** with another audit:
   ```bash
   crier audit ./posts --profile everything
   ```

## Notes

- Backfill only publishes to platforms where content is **not** already published
- Publications are recorded in the registry after success
- Failed publications can be retried by running backfill again
- Use `--dry-run` liberally to preview changes
