"""Tests for crier.converters module."""

import pytest

from crier.converters import parse_markdown_file, parse_front_matter


class TestParseFrontMatter:
    """Tests for parse_front_matter()."""

    def test_parse_valid_front_matter(self):
        content = """\
---
title: My Title
description: A description
---

Body content here.
"""
        front_matter, body = parse_front_matter(content)
        assert front_matter["title"] == "My Title"
        assert front_matter["description"] == "A description"
        assert body == "Body content here."

    def test_parse_with_tags_list(self):
        content = """\
---
title: Tagged Article
tags: [python, testing, crier]
---

Body.
"""
        front_matter, body = parse_front_matter(content)
        assert front_matter["tags"] == ["python", "testing", "crier"]

    def test_parse_without_front_matter(self):
        content = "Just plain content without front matter."
        front_matter, body = parse_front_matter(content)
        assert front_matter == {}
        assert body == content

    def test_parse_empty_front_matter(self):
        # Empty front matter requires a newline between the markers
        content = """\
---

---

Body only.
"""
        front_matter, body = parse_front_matter(content)
        assert front_matter == {}
        assert body == "Body only."

    def test_parse_malformed_yaml(self):
        content = """\
---
title: [unclosed bracket
invalid: yaml: here
---

Body.
"""
        front_matter, body = parse_front_matter(content)
        # Should return empty dict on YAML error
        assert front_matter == {}

    def test_multiline_body(self):
        content = """\
---
title: Test
---

Paragraph one.

Paragraph two.

Paragraph three.
"""
        front_matter, body = parse_front_matter(content)
        assert "Paragraph one." in body
        assert "Paragraph two." in body
        assert "Paragraph three." in body


class TestParseMarkdownFile:
    """Tests for parse_markdown_file()."""

    def test_parse_complete_file(self, sample_markdown_file):
        article = parse_markdown_file(sample_markdown_file)
        assert article.title == "Test Article Title"
        assert article.description == "A brief description"
        assert article.tags == ["python", "testing"]
        assert article.canonical_url == "https://example.com/test-article"
        assert article.published is True
        assert "body of the test article" in article.body

    def test_parse_minimal_file(self, tmp_path):
        md_file = tmp_path / "minimal.md"
        md_file.write_text("""\
---
title: Just a Title
---

Content.
""")
        article = parse_markdown_file(md_file)
        assert article.title == "Just a Title"
        assert article.description is None
        assert article.tags == []
        assert article.canonical_url is None
        assert article.published is True  # Default

    def test_parse_file_without_front_matter(self, tmp_path):
        md_file = tmp_path / "no_front_matter.md"
        md_file.write_text("Just plain markdown content.")

        article = parse_markdown_file(md_file)
        # Title defaults to filename stem
        assert article.title == "no_front_matter"
        assert article.body == "Just plain markdown content."

    def test_parse_with_comma_separated_tags(self, tmp_path):
        md_file = tmp_path / "comma_tags.md"
        md_file.write_text("""\
---
title: Comma Tags
tags: python, testing, crier
---

Body.
""")
        article = parse_markdown_file(md_file)
        assert article.tags == ["python", "testing", "crier"]

    def test_parse_with_published_false(self, tmp_path):
        md_file = tmp_path / "draft.md"
        md_file.write_text("""\
---
title: Draft Article
published: false
---

Draft content.
""")
        article = parse_markdown_file(md_file)
        assert article.published is False

    def test_parse_with_cover_image(self, tmp_path):
        md_file = tmp_path / "with_cover.md"
        md_file.write_text("""\
---
title: Article with Cover
cover_image: https://example.com/image.png
---

Content.
""")
        article = parse_markdown_file(md_file)
        # cover_image is not currently extracted by parse_markdown_file
        # but the article is still created successfully
        assert article.title == "Article with Cover"

    def test_parse_accepts_path_string(self, sample_markdown_file):
        # Should work with string path as well as Path object
        article = parse_markdown_file(str(sample_markdown_file))
        assert article.title == "Test Article Title"
