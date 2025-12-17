# dev.to

dev.to is a community of software developers. It has excellent API support for publishing articles.

## Setup

1. Go to [dev.to/settings/extensions](https://dev.to/settings/extensions)
2. Scroll to "DEV Community API Keys"
3. Generate a new API key
4. Configure Crier:

```bash
crier config set devto.api_key YOUR_API_KEY
```

## API Key Format

```
api_key
```

Just the API key string, no special formatting required.

## Features

| Feature | Supported |
|---------|:---------:|
| Publish | ✓ |
| Update | ✓ |
| List | ✓ |
| Delete | ✓ (unpublishes) |

## Notes

- **Tags**: Limited to 4 tags per article
- **Canonical URL**: Fully supported
- **Draft mode**: Supported via `--draft` flag
- **Delete**: Actually unpublishes rather than deletes

## Example

```bash
# Publish to dev.to
crier publish my-post.md --to devto

# List your articles
crier list devto

# Update an article
crier update devto 12345 --file updated-post.md
```
