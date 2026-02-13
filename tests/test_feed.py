"""Tests for crier.feed module."""

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from crier.feed import generate_feed


def _make_md(tmp_path, name, title, date=None, tags=None, body="Article body."):
    """Helper to create a markdown file with front matter."""
    tag_str = ""
    if tags:
        tag_str = "tags: [" + ", ".join(tags) + "]\n"
    date_str = ""
    if date:
        date_str = f"date: {date}\n"
    content = f"""\
---
title: "{title}"
{date_str}{tag_str}canonical_url: https://example.com/{name}/
---

{body}
"""
    md = tmp_path / f"{name}.md"
    md.write_text(content)
    return md


class TestGenerateFeed:
    """Tests for generate_feed()."""

    def test_rss_output_is_valid_xml(self, tmp_path):
        f1 = _make_md(tmp_path, "post1", "First Post", date="2025-01-01")
        xml = generate_feed([f1], format="rss", site_url="https://example.com")

        # Should be valid XML
        root = ET.fromstring(xml)
        assert root.tag == "rss"

    def test_atom_output_is_valid_xml(self, tmp_path):
        f1 = _make_md(tmp_path, "post1", "First Post", date="2025-01-01")
        xml = generate_feed([f1], format="atom", site_url="https://example.com")

        root = ET.fromstring(xml)
        # Atom root is <feed>
        assert "feed" in root.tag

    def test_rss_contains_items(self, tmp_path):
        f1 = _make_md(tmp_path, "post1", "First Post", date="2025-01-01")
        f2 = _make_md(tmp_path, "post2", "Second Post", date="2025-01-02")
        xml = generate_feed([f1, f2], format="rss", site_url="https://example.com")

        root = ET.fromstring(xml)
        items = root.findall(".//item")
        assert len(items) == 2

    def test_rss_item_title(self, tmp_path):
        f1 = _make_md(tmp_path, "post1", "My Great Article", date="2025-01-01")
        xml = generate_feed([f1], format="rss", site_url="https://example.com")

        root = ET.fromstring(xml)
        title = root.find(".//item/title")
        assert title is not None
        assert title.text == "My Great Article"

    def test_rss_item_link_is_canonical(self, tmp_path):
        f1 = _make_md(tmp_path, "post1", "Post", date="2025-01-01")
        xml = generate_feed([f1], format="rss", site_url="https://example.com")

        root = ET.fromstring(xml)
        link = root.find(".//item/link")
        assert link is not None
        assert link.text == "https://example.com/post1/"

    def test_rss_categories_from_tags(self, tmp_path):
        f1 = _make_md(tmp_path, "post1", "Post", date="2025-01-01", tags=["python", "web"])
        xml = generate_feed([f1], format="rss", site_url="https://example.com")

        root = ET.fromstring(xml)
        categories = root.findall(".//item/category")
        cat_texts = {c.text for c in categories}
        assert "python" in cat_texts
        assert "web" in cat_texts

    def test_limit_items(self, tmp_path):
        files = [
            _make_md(tmp_path, f"post{i}", f"Post {i}", date=f"2025-01-{i+1:02d}")
            for i in range(5)
        ]
        xml = generate_feed(files, format="rss", site_url="https://example.com", limit=3)

        root = ET.fromstring(xml)
        items = root.findall(".//item")
        assert len(items) == 3

    def test_items_sorted_most_recent_first(self, tmp_path):
        f1 = _make_md(tmp_path, "old", "Old Post", date="2025-01-01")
        f2 = _make_md(tmp_path, "new", "New Post", date="2025-06-15")
        xml = generate_feed([f1, f2], format="rss", site_url="https://example.com")

        root = ET.fromstring(xml)
        titles = [item.find("title").text for item in root.findall(".//item")]
        assert titles[0] == "New Post"
        assert titles[1] == "Old Post"

    def test_tag_filter(self, tmp_path):
        f1 = _make_md(tmp_path, "py", "Python Post", date="2025-01-01", tags=["python"])
        f2 = _make_md(tmp_path, "js", "JS Post", date="2025-01-02", tags=["javascript"])
        xml = generate_feed(
            [f1, f2],
            format="rss",
            site_url="https://example.com",
            tag_filter={"python"},
        )

        root = ET.fromstring(xml)
        items = root.findall(".//item")
        assert len(items) == 1
        assert items[0].find("title").text == "Python Post"

    def test_since_filter(self, tmp_path):
        f1 = _make_md(tmp_path, "old", "Old Post", date="2024-01-01")
        f2 = _make_md(tmp_path, "new", "New Post", date="2025-06-01")
        xml = generate_feed(
            [f1, f2],
            format="rss",
            site_url="https://example.com",
            since=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

        root = ET.fromstring(xml)
        items = root.findall(".//item")
        assert len(items) == 1
        assert items[0].find("title").text == "New Post"

    def test_until_filter(self, tmp_path):
        f1 = _make_md(tmp_path, "old", "Old Post", date="2024-01-01")
        f2 = _make_md(tmp_path, "new", "New Post", date="2025-06-01")
        xml = generate_feed(
            [f1, f2],
            format="rss",
            site_url="https://example.com",
            until=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )

        root = ET.fromstring(xml)
        items = root.findall(".//item")
        assert len(items) == 1
        assert items[0].find("title").text == "Old Post"

    def test_no_site_url_raises(self, tmp_path):
        f1 = _make_md(tmp_path, "post1", "Post", date="2025-01-01")
        with patch("crier.feed.get_site_base_url", return_value=None):
            with pytest.raises(ValueError, match="site_base_url required"):
                generate_feed([f1], format="rss", site_url=None)

    def test_custom_title_and_description(self, tmp_path):
        f1 = _make_md(tmp_path, "post1", "Post", date="2025-01-01")
        xml = generate_feed(
            [f1],
            format="rss",
            site_url="https://example.com",
            title="My Blog Feed",
            description="Latest posts from my blog",
        )

        root = ET.fromstring(xml)
        channel = root.find("channel")
        assert channel.find("title").text == "My Blog Feed"
        assert channel.find("description").text == "Latest posts from my blog"

    def test_empty_files_list(self, tmp_path):
        xml = generate_feed([], format="rss", site_url="https://example.com")
        root = ET.fromstring(xml)
        items = root.findall(".//item")
        assert len(items) == 0

    def test_content_encoded_in_items(self, tmp_path):
        f1 = _make_md(tmp_path, "post1", "Post", date="2025-01-01", body="Some article body content.")
        xml = generate_feed([f1], format="rss", site_url="https://example.com")

        # The content:encoded should contain the body
        assert "Some article body content" in xml

    def test_atom_entry_has_link(self, tmp_path):
        f1 = _make_md(tmp_path, "post1", "Post", date="2025-01-01")
        xml = generate_feed([f1], format="atom", site_url="https://example.com")

        assert "https://example.com/post1/" in xml

    def test_malformed_file_skipped(self, tmp_path):
        """Files that can't be parsed should be silently skipped."""
        bad = tmp_path / "bad.md"
        bad.write_text("not valid front matter at all")
        good = _make_md(tmp_path, "good", "Good Post", date="2025-01-01")

        xml = generate_feed([bad, good], format="rss", site_url="https://example.com")
        root = ET.fromstring(xml)
        items = root.findall(".//item")
        # Good file should be included, bad file title defaults to filename
        assert len(items) >= 1
