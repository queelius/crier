"""RSS/Atom feed generation for crier content."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from feedgen.feed import FeedGenerator

from .converters import parse_markdown_file
from .config import get_site_base_url
from .utils import get_content_date, get_content_tags, truncate_at_sentence


def generate_feed(
    files: list[Path],
    format: str = "rss",
    site_url: str | None = None,
    title: str | None = None,
    description: str | None = None,
    limit: int | None = None,
    tag_filter: set[str] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> str:
    """Generate an RSS or Atom feed from content files.

    Args:
        files: List of markdown file paths to include
        format: Feed format - "rss" or "atom"
        site_url: Site base URL (falls back to config)
        title: Feed title (defaults to "Content Feed")
        description: Feed description
        limit: Maximum number of items (most recent first)
        tag_filter: Only include files with these tags (case-insensitive, OR logic)
        since: Only include files dated after this
        until: Only include files dated before this

    Returns:
        XML string of the generated feed
    """
    if site_url is None:
        site_url = get_site_base_url()

    if not site_url:
        raise ValueError(
            "site_base_url required for feed generation. "
            "Set it with: crier config set site_base_url https://example.com"
        )

    # Parse and filter files
    items = _collect_items(files, site_url, tag_filter, since, until)

    # Sort by date (most recent first)
    _epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    items.sort(key=lambda x: x["date"] or _epoch, reverse=True)

    # Apply limit
    if limit:
        items = items[:limit]

    # Build feed
    fg = FeedGenerator()
    fg.id(site_url)
    fg.title(title or "Content Feed")
    fg.description(description or f"Content from {site_url}")
    fg.link(href=site_url, rel="alternate")
    fg.language("en")

    if items:
        fg.updated(items[0]["date"] or datetime.now(timezone.utc))

    for item in items:
        fe = fg.add_entry(order="append")
        fe.id(item["url"])
        fe.title(item["title"])
        fe.link(href=item["url"])

        if item["date"]:
            fe.published(item["date"])
            fe.updated(item["date"])

        if item["description"]:
            fe.summary(item["description"])

        if item["tags"]:
            for tag in item["tags"]:
                fe.category(term=tag)

        if item["body"]:
            fe.content(item["body"], type="html")

    if format == "atom":
        return fg.atom_str(pretty=True).decode("utf-8")
    else:
        return fg.rss_str(pretty=True).decode("utf-8")


def _collect_items(
    files: list[Path],
    site_url: str,
    tag_filter: set[str] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict[str, Any]]:
    """Parse files and collect feed items, applying filters."""
    items = []

    for file_path in files:
        try:
            # Apply tag filter
            if tag_filter:
                content_tags = get_content_tags(file_path)
                if not any(tag in tag_filter for tag in content_tags):
                    continue

            # Apply date filter
            content_date = get_content_date(file_path)
            if content_date:
                if content_date.tzinfo is None:
                    content_date = content_date.replace(tzinfo=timezone.utc)
                if since and content_date < since:
                    continue
                if until and content_date > until:
                    continue

            # Parse the article
            article = parse_markdown_file(str(file_path))

            if not article.title:
                continue

            # Use canonical_url or construct from site_url
            url = article.canonical_url or f"{site_url}/{file_path.stem}/"

            # Build description: use front matter description or truncate body
            description = article.description
            if not description and article.body:
                description = truncate_at_sentence(article.body, max_chars=200)

            items.append({
                "title": article.title,
                "url": url,
                "date": content_date,
                "description": description,
                "tags": article.tags or [],
                "body": article.body,
            })

        except Exception:
            continue  # Skip files that can't be parsed

    return items
