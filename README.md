# Crier

Cross-post your content to dev.to, Hashnode, Medium, and more.

Like a town crier announcing your content to the world.

## Installation

```bash
pip install crier
```

## Quick Start

```bash
# Configure your API keys
crier config set devto.api_key YOUR_DEVTO_API_KEY

# Publish a markdown file
crier publish post.md --to devto

# Publish to multiple platforms
crier publish post.md --to devto --to hashnode

# List your articles
crier list devto

# Update an existing article
crier update devto 12345 --file updated-post.md
```

## Configuration

API keys can be set via:

1. **Config file** (`~/.config/crier/config.yaml`):
   ```yaml
   platforms:
     devto:
       api_key: your_key_here
     hashnode:
       api_key: your_key_here
   ```

2. **Environment variables**:
   ```bash
   export CRIER_DEVTO_API_KEY=your_key_here
   export CRIER_HASHNODE_API_KEY=your_key_here
   ```

## Markdown Format

Crier reads standard markdown with YAML front matter:

```markdown
---
title: "My Amazing Post"
description: "A brief description"
tags: [python, programming]
canonical_url: https://myblog.com/my-post
published: true
---

Your content here...
```

## Supported Platforms

| Platform | Status |
|----------|--------|
| dev.to | Implemented |
| Hashnode | Planned |
| Medium | Planned |
| LinkedIn | Planned |
| Twitter/X | Planned |

## Commands

```bash
crier publish FILE [--to PLATFORM]...  # Publish to platform(s)
crier update PLATFORM ID --file FILE   # Update existing article
crier list PLATFORM                     # List your articles
crier config set KEY VALUE              # Set configuration
crier config show                       # Show configuration
crier platforms                         # List available platforms
```

## License

MIT
