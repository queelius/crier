"""Markdown parsing utilities."""

import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import yaml

from ..platforms.base import Article
from ..config import get_site_base_url, get_content_paths, infer_canonical_url


def resolve_relative_links(body: str, base_url: str) -> str:
    """Resolve relative links in markdown content to absolute URLs.

    Handles:
    - Markdown links: [text](/relative/path) or [text](relative/path)
    - Markdown images: ![alt](/relative/path.png)
    - HTML href: <a href="/relative/path">
    - HTML src: <img src="/relative/path.png">

    Args:
        body: Markdown content with potentially relative links
        base_url: Base URL to resolve against (e.g., https://example.com)

    Returns:
        Markdown content with relative links resolved to absolute URLs
    """
    if not base_url:
        return body

    # Ensure base_url has no trailing slash for consistent joining
    base_url = base_url.rstrip("/")

    def is_relative(url: str) -> bool:
        """Check if URL is relative (not absolute, not anchor, not protocol-relative)."""
        if not url:
            return False
        # Skip absolute URLs, anchors, protocol-relative, mailto:, tel:, etc.
        if url.startswith(("http://", "https://", "//", "#", "mailto:", "tel:", "data:")):
            return False
        return True

    def resolve(url: str) -> str:
        """Resolve a relative URL against base_url."""
        if not is_relative(url):
            return url
        if url.startswith("/"):
            # Absolute path - join with base domain
            return base_url + url
        else:
            # Relative path - join with base URL
            return urljoin(base_url + "/", url)

    # Pattern for markdown links and images: [text](url) or ![alt](url)
    # Captures: group(1) = ! or empty, group(2) = text/alt, group(3) = url
    md_link_pattern = r'(!?)\[([^\]]*)\]\(([^)]+)\)'

    def replace_md_link(match):
        prefix = match.group(1)  # ! for images, empty for links
        text = match.group(2)
        url = match.group(3).strip()
        resolved = resolve(url)
        return f"{prefix}[{text}]({resolved})"

    body = re.sub(md_link_pattern, replace_md_link, body)

    # Pattern for HTML href attributes: href="url" or href='url'
    href_pattern = r'href=(["\'])([^"\']+)\1'

    def replace_href(match):
        quote = match.group(1)
        url = match.group(2)
        resolved = resolve(url)
        return f'href={quote}{resolved}{quote}'

    body = re.sub(href_pattern, replace_href, body)

    # Pattern for HTML src attributes: src="url" or src='url'
    src_pattern = r'src=(["\'])([^"\']+)\1'

    def replace_src(match):
        quote = match.group(1)
        url = match.group(2)
        resolved = resolve(url)
        return f'src={quote}{resolved}{quote}'

    body = re.sub(src_pattern, replace_src, body)

    return body


def parse_front_matter(content: str) -> tuple[dict[str, Any], str]:
    """Parse front matter from markdown content (YAML or TOML).

    Supports:
        - YAML front matter between ``---`` markers
        - TOML front matter between ``+++`` markers

    Returns:
        Tuple of (front_matter_dict, body_content)
    """
    # Match YAML front matter between --- markers
    yaml_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(yaml_pattern, content, re.DOTALL)

    if match:
        front_matter_str = match.group(1)
        body = match.group(2).strip()

        try:
            front_matter = yaml.safe_load(front_matter_str) or {}
        except yaml.YAMLError:
            front_matter = {}

        return front_matter, body

    # Match TOML front matter between +++ markers
    toml_pattern = r'^\+\+\+\s*\n(.*?)\n\+\+\+\s*\n(.*)$'
    match = re.match(toml_pattern, content, re.DOTALL)

    if match:
        front_matter_str = match.group(1)
        body = match.group(2).strip()

        try:
            front_matter = _parse_toml(front_matter_str)
        except Exception:
            front_matter = {}

        return front_matter, body

    # No front matter found
    return {}, content.strip()


def _parse_toml(toml_str: str) -> dict[str, Any]:
    """Parse TOML front matter string into a dict.

    Uses tomllib (Python 3.11+) with fallback to a basic key=value parser.
    """
    try:
        import tomllib
        return tomllib.loads(toml_str)
    except ImportError:
        pass

    # Basic fallback for Python 3.10: parse simple key = value pairs
    result: dict[str, Any] = {}
    for line in toml_str.strip().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('['):
            continue
        if '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip()
        value = value.strip()
        # Strip quotes
        if (value.startswith("'") and value.endswith("'")) or \
           (value.startswith('"') and value.endswith('"')):
            value = value[1:-1]
        # Parse arrays
        elif value.startswith('[') and value.endswith(']'):
            inner = value[1:-1]
            items = [
                item.strip().strip("'\"")
                for item in inner.split(',')
                if item.strip()
            ]
            result[key] = items
            continue
        # Parse booleans
        elif value == 'true':
            result[key] = True
            continue
        elif value == 'false':
            result[key] = False
            continue
        result[key] = value
    return result


def parse_markdown_file(
    path: str | Path,
    content_root: str | Path | None = None,
    base_url: str | None = None,
) -> Article:
    """Parse a markdown file into an Article.

    Extracts front matter and body content. If canonical_url is not in front matter
    and site_base_url is configured, infers it from the file path using Hugo conventions.

    Args:
        path: Path to the markdown file
        content_root: Root of content directory for URL inference (optional)
        base_url: Site base URL for URL inference (optional, uses config if not provided)
    """
    path = Path(path)
    content = path.read_text()

    front_matter, body = parse_front_matter(content)

    # Extract common fields from front matter
    title = front_matter.get("title", path.stem)
    description = front_matter.get("description")
    raw_tags = front_matter.get("tags", [])
    canonical_url = front_matter.get("canonical_url")
    published = front_matter.get("published", True)
    cover_image = front_matter.get("cover_image") or front_matter.get("image")

    # Infer canonical_url if not present and we have config
    if not canonical_url:
        # Get base_url from config if not provided
        if base_url is None:
            base_url = get_site_base_url()

        # Get content_root from config if not provided
        if content_root is None:
            content_paths = get_content_paths()
            if content_paths:
                # Try each content path to find one that contains this file
                for cp in content_paths:
                    cp_path = Path(cp).resolve()
                    try:
                        path.resolve().relative_to(cp_path)
                        content_root = cp_path
                        break
                    except ValueError:
                        continue

        # Infer URL if we have both base_url and content_root
        if base_url and content_root:
            canonical_url = infer_canonical_url(path, content_root, base_url)

    # Handle tags as list or comma-separated string
    if isinstance(raw_tags, list):
        tags = raw_tags
    elif isinstance(raw_tags, str):
        # Split comma-separated tags and strip whitespace
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    else:
        tags = []

    # Resolve relative links to absolute URLs using site_base_url
    # This ensures links work correctly when cross-posted to other platforms
    if base_url:
        body = resolve_relative_links(body, base_url)

    return Article(
        title=title,
        body=body,
        description=description,
        tags=tags,
        canonical_url=canonical_url,
        published=published,
        cover_image=cover_image,
    )
