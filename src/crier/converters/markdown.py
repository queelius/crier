"""Markdown parsing utilities."""

import re
from pathlib import Path
from typing import Any

import yaml

from ..platforms.base import Article
from ..config import get_site_base_url, get_content_paths, infer_canonical_url


def parse_front_matter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML front matter from markdown content.

    Returns:
        Tuple of (front_matter_dict, body_content)
    """
    # Match YAML front matter between --- markers
    pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(pattern, content, re.DOTALL)

    if match:
        front_matter_str = match.group(1)
        body = match.group(2).strip()

        try:
            front_matter = yaml.safe_load(front_matter_str) or {}
        except yaml.YAMLError:
            front_matter = {}

        return front_matter, body

    # No front matter found
    return {}, content.strip()


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

    return Article(
        title=title,
        body=body,
        description=description,
        tags=tags,
        canonical_url=canonical_url,
        published=published,
        cover_image=cover_image,
    )
