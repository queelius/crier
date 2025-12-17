# Configuration

Crier stores configuration in `~/.config/crier/config.yaml`.

## Setting API Keys

### Via CLI

```bash
crier config set devto.api_key YOUR_KEY
crier config set bluesky.api_key "handle.bsky.social:app-password"
```

### Via Environment Variables

Environment variables take precedence over the config file:

```bash
export CRIER_DEVTO_API_KEY=your_key
export CRIER_BLUESKY_API_KEY="handle.bsky.social:app-password"
```

### Via Config File

Edit `~/.config/crier/config.yaml` directly:

```yaml
platforms:
  devto:
    api_key: your_key_here
  bluesky:
    api_key: "handle.bsky.social:app-password"
  mastodon:
    api_key: "mastodon.social:access-token"
```

## Publishing Profiles

Profiles let you group platforms for convenience.

### Creating Profiles

```bash
# Create basic profiles
crier config profile set blogs devto hashnode ghost
crier config profile set social bluesky mastodon

# Profiles can reference other profiles (composition)
crier config profile set everything blogs social
```

### Using Profiles

```bash
# Publish to all platforms in a profile
crier publish post.md --profile blogs

# Combine profile with additional platforms
crier publish post.md --profile blogs --to telegram

# Audit against a profile
crier audit ./posts --profile social

# Backfill using a profile
crier backfill ./posts --profile everything
```

### Managing Profiles

```bash
# Show all profiles
crier config profile show

# Show a specific profile
crier config profile show blogs

# Delete a profile
crier config profile delete old-profile
```

### Config File Format

```yaml
platforms:
  devto:
    api_key: xxx
  bluesky:
    api_key: handle.bsky.social:xxx

profiles:
  blogs:
    - devto
    - hashnode
    - ghost
  social:
    - bluesky
    - mastodon
  everything:
    - blogs
    - social
```

## Viewing Configuration

```bash
# Show configured platforms and profiles (keys are masked)
crier config show

# Validate API keys work
crier doctor

# List all available platforms
crier platforms
```

## Configuration Path

Override the config file location:

```bash
export CRIER_CONFIG=/path/to/config.yaml
```
