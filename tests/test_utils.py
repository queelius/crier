"""Tests for crier.utils — shared utility functions."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from crier.utils import (
    truncate_at_sentence,
    has_valid_front_matter,
    is_in_content_paths,
    matches_exclude_pattern,
    parse_date_filter,
    get_content_date,
    get_content_tags,
    find_content_files,
)


class TestTruncateAtSentence:
    """Tests for truncate_at_sentence()."""

    def test_short_text_unchanged(self):
        assert truncate_at_sentence("Hello world.", 100) == "Hello world."

    def test_exact_length_unchanged(self):
        text = "a" * 50
        assert truncate_at_sentence(text, 50) == text

    def test_truncate_at_period(self):
        text = "First sentence. Second sentence. Third sentence is long."
        result = truncate_at_sentence(text, 35)
        assert result == "First sentence. Second sentence."

    def test_truncate_at_question_mark(self):
        text = "Is this a question? Yes it is a rather long answer."
        result = truncate_at_sentence(text, 25)
        assert result == "Is this a question?"

    def test_truncate_at_exclamation(self):
        # "!" must be past halfway for sentence boundary to be used
        text = "This is great! And then there is more text after it."
        result = truncate_at_sentence(text, 20)
        assert result == "This is great!"

    def test_sentence_boundary_too_early_falls_to_word(self):
        # "!" at position 3 is below 50% of 10 — word boundary used
        text = "Wow! That was unexpected and this goes on."
        result = truncate_at_sentence(text, 10)
        # Falls to word boundary + "..." appended
        assert result.endswith("...")

    def test_fallback_to_word_boundary(self):
        text = "word " * 20
        result = truncate_at_sentence(text, 30)
        assert result.endswith("...")

    def test_hard_truncate_no_boundaries(self):
        text = "x" * 200
        result = truncate_at_sentence(text, 50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_sentence_boundary_must_be_past_halfway(self):
        text = "Hi.  " + "x" * 200
        result = truncate_at_sentence(text, 100)
        assert len(result) <= 100

    def test_empty_text(self):
        assert truncate_at_sentence("", 100) == ""

    def test_max_chars_zero(self):
        result = truncate_at_sentence("Hello", 0)
        assert len(result) <= 3

    def test_multiple_sentence_types(self):
        text = "Question? Statement. Exclamation! And more after."
        result = truncate_at_sentence(text, 35)
        # Should cut at "!" (position 31)
        assert result == "Question? Statement. Exclamation!"


class TestHasValidFrontMatter:
    """Tests for has_valid_front_matter()."""

    def test_valid_with_title(self, tmp_path):
        f = tmp_path / "good.md"
        f.write_text("---\ntitle: Hello\n---\nBody text")
        assert has_valid_front_matter(f) is True

    def test_derives_title_from_filename(self, tmp_path):
        # parse_markdown_file derives title from filename when not in YAML
        f = tmp_path / "my_article.md"
        f.write_text("---\ntags: [a]\n---\nBody text")
        assert has_valid_front_matter(f) is True

    def test_no_front_matter_still_derives_title(self, tmp_path):
        # parse_markdown_file derives title from filename
        f = tmp_path / "plain.md"
        f.write_text("Just plain text with no front matter.")
        assert has_valid_front_matter(f) is True

    def test_nonexistent_file(self, tmp_path):
        f = tmp_path / "nope.md"
        assert has_valid_front_matter(f) is False

    def test_empty_file_derives_title(self, tmp_path):
        # parse_markdown_file derives title from filename even for empty
        f = tmp_path / "empty.md"
        f.write_text("")
        assert has_valid_front_matter(f) is True

    def test_empty_title_string(self, tmp_path):
        f = tmp_path / "empty_title.md"
        f.write_text('---\ntitle: ""\n---\nBody')
        assert has_valid_front_matter(f) is False


class TestIsInContentPaths:
    """Tests for is_in_content_paths()."""

    def test_file_in_content_path(self, tmp_path, monkeypatch):
        content_dir = tmp_path / "posts"
        content_dir.mkdir()
        f = content_dir / "article.md"
        f.touch()

        monkeypatch.setattr(
            "crier.config.get_content_paths",
            lambda: [str(content_dir)],
        )
        assert is_in_content_paths(f) is True

    def test_file_not_in_content_path(self, tmp_path, monkeypatch):
        content_dir = tmp_path / "posts"
        content_dir.mkdir()
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        f = other_dir / "article.md"
        f.touch()

        monkeypatch.setattr(
            "crier.config.get_content_paths",
            lambda: [str(content_dir)],
        )
        assert is_in_content_paths(f) is False

    def test_no_content_paths_configured(self, monkeypatch):
        monkeypatch.setattr(
            "crier.config.get_content_paths",
            lambda: [],
        )
        assert is_in_content_paths(Path("/some/file.md")) is False

    def test_nested_file_in_content_path(self, tmp_path, monkeypatch):
        content_dir = tmp_path / "posts"
        nested = content_dir / "2025" / "january"
        nested.mkdir(parents=True)
        f = nested / "deep.md"
        f.touch()

        monkeypatch.setattr(
            "crier.config.get_content_paths",
            lambda: [str(content_dir)],
        )
        assert is_in_content_paths(f) is True


class TestMatchesExcludePattern:
    """Tests for matches_exclude_pattern()."""

    def test_exact_match(self):
        assert matches_exclude_pattern("_index.md", ["_index.md"]) is True

    def test_no_match(self):
        assert matches_exclude_pattern("article.md", ["_index.md"]) is False

    def test_prefix_wildcard(self):
        assert matches_exclude_pattern("draft-foo.md", ["draft-*"]) is True

    def test_suffix_wildcard(self):
        assert matches_exclude_pattern("foo.draft.md", ["*.draft.md"]) is True

    def test_multiple_patterns(self):
        patterns = ["_index.md", "draft-*", "*.bak"]
        assert matches_exclude_pattern("draft-test.md", patterns) is True
        assert matches_exclude_pattern("article.bak", patterns) is True
        assert matches_exclude_pattern("article.md", patterns) is False

    def test_empty_patterns(self):
        assert matches_exclude_pattern("anything.md", []) is False

    def test_star_matches_all(self):
        assert matches_exclude_pattern("anything.md", ["*"]) is True


class TestParseDateFilter:
    """Tests for parse_date_filter()."""

    def test_days_relative(self):
        result = parse_date_filter("7d")
        expected = datetime.now() - timedelta(days=7)
        assert abs((result - expected).total_seconds()) < 2

    def test_weeks_relative(self):
        result = parse_date_filter("2w")
        expected = datetime.now() - timedelta(weeks=2)
        assert abs((result - expected).total_seconds()) < 2

    def test_months_relative(self):
        result = parse_date_filter("1m")
        expected = datetime.now() - timedelta(days=30)
        assert abs((result - expected).total_seconds()) < 2

    def test_years_relative(self):
        result = parse_date_filter("1y")
        expected = datetime.now() - timedelta(days=365)
        assert abs((result - expected).total_seconds()) < 2

    def test_absolute_date(self):
        result = parse_date_filter("2025-01-15")
        assert result == datetime(2025, 1, 15)

    def test_absolute_datetime(self):
        result = parse_date_filter("2025-01-15T12:30:00")
        assert result == datetime(2025, 1, 15, 12, 30, 0)

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Invalid date format"):
            parse_date_filter("not-a-date")

    def test_case_insensitive(self):
        result = parse_date_filter("7D")
        expected = datetime.now() - timedelta(days=7)
        assert abs((result - expected).total_seconds()) < 2

    def test_zero_days(self):
        result = parse_date_filter("0d")
        expected = datetime.now()
        assert abs((result - expected).total_seconds()) < 2


class TestGetContentDate:
    """Tests for get_content_date()."""

    def test_yaml_date_string(self, tmp_path):
        f = tmp_path / "article.md"
        f.write_text("---\ntitle: Test\ndate: 2025-03-15\n---\nBody")
        result = get_content_date(f)
        assert result is not None
        assert result.year == 2025
        assert result.month == 3
        assert result.day == 15

    def test_yaml_datetime_string(self, tmp_path):
        f = tmp_path / "article.md"
        f.write_text("---\ntitle: Test\ndate: 2025-03-15T10:30:00\n---\nBody")
        result = get_content_date(f)
        assert result is not None
        assert result.hour == 10

    def test_no_date_field(self, tmp_path):
        f = tmp_path / "article.md"
        f.write_text("---\ntitle: Test\n---\nBody")
        assert get_content_date(f) is None

    def test_no_front_matter(self, tmp_path):
        f = tmp_path / "article.md"
        f.write_text("Just plain text")
        assert get_content_date(f) is None

    def test_invalid_file(self, tmp_path):
        f = tmp_path / "nope.md"
        assert get_content_date(f) is None

    def test_date_with_timezone_z(self, tmp_path):
        f = tmp_path / "article.md"
        f.write_text("---\ntitle: Test\ndate: '2025-03-15T10:00:00Z'\n---\nBody")
        result = get_content_date(f)
        assert result is not None
        assert result.year == 2025

    def test_yaml_auto_parsed_date(self, tmp_path):
        # YAML auto-parses dates like 2025-03-15 as date objects
        f = tmp_path / "article.md"
        f.write_text("---\ntitle: Test\ndate: 2025-03-15\n---\nBody")
        result = get_content_date(f)
        assert isinstance(result, datetime)


class TestGetContentTags:
    """Tests for get_content_tags()."""

    def test_list_format(self, tmp_path):
        f = tmp_path / "article.md"
        f.write_text("---\ntitle: Test\ntags: [Python, Testing]\n---\nBody")
        result = get_content_tags(f)
        assert result == ["python", "testing"]

    def test_string_format(self, tmp_path):
        f = tmp_path / "article.md"
        f.write_text('---\ntitle: Test\ntags: "Python, Testing"\n---\nBody')
        result = get_content_tags(f)
        assert result == ["python", "testing"]

    def test_no_tags(self, tmp_path):
        f = tmp_path / "article.md"
        f.write_text("---\ntitle: Test\n---\nBody")
        assert get_content_tags(f) == []

    def test_no_front_matter(self, tmp_path):
        f = tmp_path / "article.md"
        f.write_text("Just plain text")
        assert get_content_tags(f) == []

    def test_empty_tags_list(self, tmp_path):
        f = tmp_path / "article.md"
        f.write_text("---\ntitle: Test\ntags: []\n---\nBody")
        assert get_content_tags(f) == []

    def test_tags_normalized_lowercase(self, tmp_path):
        f = tmp_path / "article.md"
        f.write_text("---\ntitle: Test\ntags: [UPPER, Mixed]\n---\nBody")
        result = get_content_tags(f)
        assert result == ["upper", "mixed"]

    def test_single_tag(self, tmp_path):
        f = tmp_path / "article.md"
        f.write_text("---\ntitle: Test\ntags: [python]\n---\nBody")
        assert get_content_tags(f) == ["python"]


class TestFindContentFiles:
    """Tests for find_content_files()."""

    def test_explicit_file_path(self, tmp_path):
        f = tmp_path / "article.md"
        f.write_text("---\ntitle: Test\n---\nBody")
        result = find_content_files(str(f))
        assert len(result) == 1
        assert result[0].name == "article.md"

    def test_explicit_directory(self, tmp_path):
        d = tmp_path / "posts"
        d.mkdir()
        f1 = d / "one.md"
        f1.write_text("---\ntitle: One\n---\nBody")
        f2 = d / "two.md"
        f2.write_text("---\ntitle: Two\n---\nBody")
        result = find_content_files(str(d))
        assert len(result) == 2

    def test_includes_files_with_derived_titles(self, tmp_path):
        # parse_markdown_file derives titles from filenames,
        # so even files without YAML front matter pass validation
        d = tmp_path / "posts"
        d.mkdir()
        good = d / "good.md"
        good.write_text("---\ntitle: Good\n---\nBody")
        derived = d / "derived.md"
        derived.write_text("No front matter but filename becomes title")
        result = find_content_files(str(d))
        assert len(result) == 2

    def test_exclude_patterns_applied(self, tmp_path, monkeypatch):
        d = tmp_path / "posts"
        d.mkdir()
        f1 = d / "article.md"
        f1.write_text("---\ntitle: Article\n---\nBody")
        f2 = d / "_index.md"
        f2.write_text("---\ntitle: Index\n---\nBody")

        monkeypatch.setattr(
            "crier.config.get_exclude_patterns",
            lambda: ["_index.md"],
        )
        monkeypatch.setattr(
            "crier.config.get_file_extensions",
            lambda: [".md"],
        )
        result = find_content_files(str(d))
        assert len(result) == 1
        assert result[0].name == "article.md"

    def test_no_content_paths_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            "crier.config.get_content_paths",
            lambda: [],
        )
        monkeypatch.setattr(
            "crier.config.get_exclude_patterns",
            lambda: [],
        )
        monkeypatch.setattr(
            "crier.config.get_file_extensions",
            lambda: [".md"],
        )
        result = find_content_files()
        assert result == []

    def test_uses_configured_content_paths(self, tmp_path, monkeypatch):
        d = tmp_path / "content"
        d.mkdir()
        f = d / "post.md"
        f.write_text("---\ntitle: Post\n---\nBody")

        monkeypatch.setattr(
            "crier.config.get_content_paths",
            lambda: [str(d)],
        )
        monkeypatch.setattr(
            "crier.config.get_exclude_patterns",
            lambda: [],
        )
        monkeypatch.setattr(
            "crier.config.get_file_extensions",
            lambda: [".md"],
        )
        result = find_content_files()
        assert len(result) == 1

    def test_custom_file_extensions(self, tmp_path, monkeypatch):
        d = tmp_path / "posts"
        d.mkdir()
        f_md = d / "post.md"
        f_md.write_text("---\ntitle: MD\n---\nBody")
        f_rst = d / "post.rst"
        f_rst.write_text("---\ntitle: RST\n---\nBody")

        monkeypatch.setattr(
            "crier.config.get_exclude_patterns",
            lambda: [],
        )
        monkeypatch.setattr(
            "crier.config.get_file_extensions",
            lambda: [".md"],
        )
        result = find_content_files(str(d))
        assert len(result) == 1
        assert result[0].name == "post.md"

    def test_resolves_content_paths_against_site_root(self, tmp_path, monkeypatch):
        """Relative content_paths resolve against site_root, not CWD."""
        site = tmp_path / "mysite"
        content = site / "content" / "post" / "hello"
        content.mkdir(parents=True)
        (content / "index.md").write_text("---\ntitle: Hello\n---\nHi")

        config_file = tmp_path / "config.yaml"
        import yaml
        config_file.write_text(yaml.dump({
            "site_root": str(site),
            "content_paths": ["content"],
            "file_extensions": [".md"],
            "exclude_patterns": [],
        }))
        monkeypatch.setenv("CRIER_CONFIG", str(config_file))
        monkeypatch.chdir(tmp_path)  # CWD is NOT the site

        files = find_content_files()
        assert len(files) == 1
        assert files[0].name == "index.md"

    def test_is_in_content_paths_resolves_against_site_root(self, tmp_path, monkeypatch):
        """is_in_content_paths resolves relative paths against site_root."""
        site = tmp_path / "mysite"
        content = site / "content" / "post.md"
        content.parent.mkdir(parents=True)
        content.write_text("---\ntitle: Test\n---\nBody")

        config_file = tmp_path / "config.yaml"
        import yaml
        config_file.write_text(yaml.dump({
            "site_root": str(site),
            "content_paths": ["content"],
        }))
        monkeypatch.setenv("CRIER_CONFIG", str(config_file))
        monkeypatch.chdir(tmp_path)  # CWD is NOT the site

        assert is_in_content_paths(content) is True
