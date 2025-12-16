"""Markdown parsing utilities."""

import re
from pathlib import Path
from typing import Any

import yaml

from ..platforms.base import Article


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


def parse_markdown_file(path: str | Path) -> Article:
    """Parse a markdown file into an Article.

    Extracts front matter and body content.
    """
    path = Path(path)
    content = path.read_text()

    front_matter, body = parse_front_matter(content)

    # Extract common fields from front matter
    title = front_matter.get("title", path.stem)
    description = front_matter.get("description")
    tags = front_matter.get("tags", [])
    canonical_url = front_matter.get("canonical_url")
    published = front_matter.get("published", True)

    return Article(
        title=title,
        body=body,
        description=description,
        tags=tags if isinstance(tags, list) else [tags],
        canonical_url=canonical_url,
        published=published,
    )
