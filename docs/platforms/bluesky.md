# Bluesky

Bluesky is a decentralized social network. Crier creates short announcement posts with link cards.

## Setup

1. Go to Settings → App Passwords in Bluesky
2. Create a new app password
3. Configure Crier:

```bash
crier config set bluesky.api_key "yourhandle.bsky.social:xxxx-xxxx-xxxx-xxxx"
```

## API Key Format

```
handle:app_password
```

- `handle`: Your full Bluesky handle (e.g., `alice.bsky.social`)
- `app_password`: The app password you generated

## Features

| Feature | Supported |
|---------|:---------:|
| Publish | ✓ |
| Update | ✗ |
| List | ✓ |
| Delete | ✓ |

## Post Format

Crier creates posts in this format:

```
Title of Your Post

Description (if provided)

#hashtag1 #hashtag2

https://your-canonical-url.com
```

Posts are limited to 300 characters. Crier automatically truncates if needed.

## Example

```bash
crier publish my-post.md --to bluesky
```
