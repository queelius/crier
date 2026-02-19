"""Tests for pre-publish content validation (checker module)."""

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import yaml
from click.testing import CliRunner

from crier.checker import (
    CheckResult,
    CheckReport,
    check_article,
    check_content,
    check_external_links,
    check_file,
    check_front_matter,
    check_platform_specific,
    get_effective_severity,
)
from crier.cli import cli


# ── Helpers ──────────────────────────────────────────────


def _make_md(tmp_path, front_matter: dict, body: str = "This is some content.") -> Path:
    """Create a markdown file with given front matter and body."""
    fm_str = yaml.dump(front_matter, default_flow_style=False)
    content = f"---\n{fm_str}---\n\n{body}\n"
    md_file = tmp_path / "test_article.md"
    md_file.write_text(content)
    return md_file


def _make_md_raw(tmp_path, raw_content: str) -> Path:
    """Create a markdown file with raw content (no templating)."""
    md_file = tmp_path / "test_article.md"
    md_file.write_text(raw_content)
    return md_file


# ── CheckResult / CheckReport dataclass tests ───────────


class TestCheckResult:
    def test_basic_fields(self):
        r = CheckResult(severity="error", check_name="missing-title", message="No title")
        assert r.severity == "error"
        assert r.check_name == "missing-title"
        assert r.message == "No title"
        assert r.line is None
        assert r.platform is None

    def test_optional_fields(self):
        r = CheckResult(
            severity="warning",
            check_name="bluesky-length",
            message="Too long",
            line=42,
            platform="bluesky",
        )
        assert r.line == 42
        assert r.platform == "bluesky"


class TestCheckReport:
    def test_empty_report_passes(self):
        report = CheckReport(file="test.md")
        assert report.passed is True
        assert report.has_errors is False
        assert report.has_warnings is False

    def test_report_with_error(self):
        report = CheckReport(
            file="test.md",
            results=[CheckResult(severity="error", check_name="missing-title", message="No title")],
        )
        assert report.passed is False
        assert report.has_errors is True

    def test_report_with_warning_passes(self):
        report = CheckReport(
            file="test.md",
            results=[CheckResult(severity="warning", check_name="missing-date", message="No date")],
        )
        assert report.passed is True
        assert report.has_errors is False
        assert report.has_warnings is True

    def test_report_with_info_only(self):
        report = CheckReport(
            file="test.md",
            results=[CheckResult(severity="info", check_name="future-date", message="Future date")],
        )
        assert report.passed is True
        assert report.has_warnings is False

    def test_report_mixed_severities(self):
        report = CheckReport(
            file="test.md",
            results=[
                CheckResult(severity="error", check_name="empty-body", message="Empty"),
                CheckResult(severity="warning", check_name="missing-tags", message="No tags"),
                CheckResult(severity="info", check_name="future-date", message="Future"),
            ],
        )
        assert report.passed is False
        assert report.has_errors is True
        assert report.has_warnings is True

    def test_with_elevated_warnings(self):
        report = CheckReport(
            file="test.md",
            results=[
                CheckResult(severity="warning", check_name="missing-date", message="No date"),
                CheckResult(severity="info", check_name="future-date", message="Future"),
            ],
        )
        assert report.passed is True  # No errors

        elevated = report.with_elevated_warnings()
        assert elevated.passed is False  # Warning promoted to error
        assert elevated.has_errors is True
        # Info should not be promoted
        info_results = [r for r in elevated.results if r.check_name == "future-date"]
        assert info_results[0].severity == "info"

    def test_with_elevated_warnings_preserves_original(self):
        """with_elevated_warnings returns a new report, not mutating the original."""
        report = CheckReport(
            file="test.md",
            results=[CheckResult(severity="warning", check_name="x", message="m")],
        )
        elevated = report.with_elevated_warnings()
        assert report.passed is True  # Original unchanged
        assert elevated.passed is False  # New report has error

    def test_with_elevated_warnings_empty_report(self):
        report = CheckReport(file="test.md")
        elevated = report.with_elevated_warnings()
        assert elevated.passed is True
        assert len(elevated.results) == 0


# ── check_article tests ─────────────────────────────────


class TestCheckArticle:
    def test_pure_validation_no_io(self):
        """check_article is a pure function — no file or config I/O."""
        fm = {
            "title": "Test Article",
            "date": "2025-01-01",
            "tags": ["test"],
            "description": "A test",
        }
        body = " ".join(["word"] * 100)
        results = check_article(fm, body, site_base_url="https://example.com")
        errors = [r for r in results if r.severity == "error"]
        assert len(errors) == 0

    def test_with_platforms(self):
        body = "A" * 301
        results = check_article({"title": "T"}, body, platforms=["bluesky"])
        assert any(r.check_name == "bluesky-length" for r in results)

    def test_with_overrides(self):
        results = check_article(
            {"title": "T"}, "body",
            severity_overrides={"missing-tags": "disabled"},
        )
        assert not any(r.check_name == "missing-tags" for r in results)


# ── Severity override tests ──────────────────────────────


class TestEffectiveSeverity:
    def test_default_severity(self):
        assert get_effective_severity("missing-title") == "error"
        assert get_effective_severity("missing-date") == "warning"
        assert get_effective_severity("future-date") == "info"

    def test_override_severity(self):
        overrides = {"missing-date": "error"}
        assert get_effective_severity("missing-date", overrides) == "error"

    def test_disable_check(self):
        overrides = {"missing-tags": "disabled"}
        assert get_effective_severity("missing-tags", overrides) is None

    def test_unknown_check(self):
        assert get_effective_severity("nonexistent-check") is None

    def test_override_does_not_affect_other_checks(self):
        overrides = {"missing-date": "error"}
        assert get_effective_severity("missing-title", overrides) == "error"  # still default


# ── Front matter check tests ────────────────────────────


class TestCheckFrontMatter:
    def test_complete_front_matter(self):
        fm = {
            "title": "My Article",
            "date": "2025-01-01",
            "tags": ["python", "testing"],
            "description": "A description",
        }
        results = check_front_matter(fm)
        # Should only have future-date possible, but date is in the past
        errors = [r for r in results if r.severity == "error"]
        assert len(errors) == 0

    def test_missing_title(self):
        results = check_front_matter({})
        assert any(r.check_name == "missing-title" for r in results)
        title_check = next(r for r in results if r.check_name == "missing-title")
        assert title_check.severity == "error"

    def test_empty_title(self):
        results = check_front_matter({"title": ""})
        assert any(r.check_name == "missing-title" for r in results)

    def test_missing_date(self):
        results = check_front_matter({"title": "Test"})
        assert any(r.check_name == "missing-date" for r in results)

    def test_future_date_string(self):
        future = (date.today() + timedelta(days=30)).isoformat()
        results = check_front_matter({"title": "Test", "date": future})
        assert any(r.check_name == "future-date" for r in results)

    def test_future_date_object(self):
        future = date.today() + timedelta(days=30)
        results = check_front_matter({"title": "Test", "date": future})
        assert any(r.check_name == "future-date" for r in results)

    def test_past_date_no_future_warning(self):
        past = (date.today() - timedelta(days=30)).isoformat()
        results = check_front_matter({"title": "Test", "date": past})
        assert not any(r.check_name == "future-date" for r in results)

    def test_missing_tags(self):
        results = check_front_matter({"title": "Test"})
        assert any(r.check_name == "missing-tags" for r in results)

    def test_empty_tags(self):
        results = check_front_matter({"title": "Test", "tags": []})
        assert any(r.check_name == "empty-tags" for r in results)

    def test_tags_present_no_empty_warning(self):
        results = check_front_matter({"title": "Test", "tags": ["python"]})
        assert not any(r.check_name == "empty-tags" for r in results)
        assert not any(r.check_name == "missing-tags" for r in results)

    def test_title_length_ok(self):
        results = check_front_matter({"title": "Short title"})
        assert not any(r.check_name == "title-length" for r in results)

    def test_title_too_long(self):
        long_title = "A" * 101
        results = check_front_matter({"title": long_title})
        assert any(r.check_name == "title-length" for r in results)

    def test_title_exactly_100(self):
        title = "A" * 100
        results = check_front_matter({"title": title})
        assert not any(r.check_name == "title-length" for r in results)

    def test_missing_description(self):
        results = check_front_matter({"title": "Test"})
        assert any(r.check_name == "missing-description" for r in results)

    def test_description_present(self):
        results = check_front_matter({"title": "Test", "description": "Desc"})
        assert not any(r.check_name == "missing-description" for r in results)

    def test_excerpt_counts_as_description(self):
        results = check_front_matter({"title": "Test", "excerpt": "Excerpt"})
        assert not any(r.check_name == "missing-description" for r in results)

    def test_summary_counts_as_description(self):
        results = check_front_matter({"title": "Test", "summary": "Summary text"})
        assert not any(r.check_name == "missing-description" for r in results)

    def test_disabled_check_not_reported(self):
        overrides = {"missing-tags": "disabled"}
        results = check_front_matter({"title": "Test"}, severity_overrides=overrides)
        assert not any(r.check_name == "missing-tags" for r in results)

    def test_overridden_severity(self):
        overrides = {"missing-date": "error"}
        results = check_front_matter({"title": "Test"}, severity_overrides=overrides)
        date_check = next(r for r in results if r.check_name == "missing-date")
        assert date_check.severity == "error"

    def test_unparseable_date_skipped(self):
        results = check_front_matter({"title": "Test", "date": "not-a-date"})
        # Should not crash, should not report future-date
        assert not any(r.check_name == "future-date" for r in results)


# ── Content check tests ─────────────────────────────────


class TestCheckContent:
    def test_normal_content(self):
        body = " ".join(["word"] * 100)
        results = check_content(body)
        assert not any(r.check_name == "empty-body" for r in results)
        assert not any(r.check_name == "short-body" for r in results)

    def test_empty_body(self):
        results = check_content("")
        assert any(r.check_name == "empty-body" for r in results)

    def test_whitespace_only_body(self):
        results = check_content("   \n\n  ")
        assert any(r.check_name == "empty-body" for r in results)

    def test_short_body(self):
        results = check_content("Just a few words here.")
        assert any(r.check_name == "short-body" for r in results)
        short_check = next(r for r in results if r.check_name == "short-body")
        assert "under 50" in short_check.message

    def test_exactly_50_words_no_warning(self):
        body = " ".join(["word"] * 50)
        results = check_content(body)
        assert not any(r.check_name == "short-body" for r in results)

    def test_relative_link_without_base_url(self):
        body = "Check [this link](/posts/other-article/) for more."
        results = check_content(body, site_base_url=None)
        assert any(r.check_name == "broken-relative-links" for r in results)

    def test_relative_link_with_base_url(self):
        body = "Check [this link](/posts/other-article/) for more."
        results = check_content(body, site_base_url="https://example.com")
        assert not any(r.check_name == "broken-relative-links" for r in results)

    def test_absolute_link_no_warning(self):
        body = "Check [this](https://example.com/page) for more."
        results = check_content(body, site_base_url=None)
        assert not any(r.check_name == "broken-relative-links" for r in results)

    def test_relative_link_line_number(self):
        body = "Line 1\nLine 2\n[link](./relative)\nLine 4"
        results = check_content(body, site_base_url=None)
        link_check = next(r for r in results if r.check_name == "broken-relative-links")
        assert link_check.line == 3

    def test_image_missing_alt_text(self):
        body = "Some text\n![](image.png)\nMore text"
        results = check_content(body)
        assert any(r.check_name == "image-alt-text" for r in results)

    def test_image_with_alt_text(self):
        body = "Some text\n![A description](image.png)\nMore text"
        results = check_content(body)
        assert not any(r.check_name == "image-alt-text" for r in results)

    def test_image_alt_text_line_number(self):
        body = "Line 1\nLine 2\n![](pic.png)"
        results = check_content(body)
        alt_check = next(r for r in results if r.check_name == "image-alt-text")
        assert alt_check.line == 3

    def test_empty_body_short_circuits(self):
        """Empty body should not also report short-body."""
        results = check_content("")
        assert any(r.check_name == "empty-body" for r in results)
        assert not any(r.check_name == "short-body" for r in results)


# ── Platform-specific check tests ───────────────────────


class TestCheckPlatformSpecific:
    def test_bluesky_short_content_ok(self):
        results = check_platform_specific("Short post", {}, ["bluesky"])
        assert not any(r.check_name == "bluesky-length" for r in results)

    def test_bluesky_long_content(self):
        body = "A" * 301
        results = check_platform_specific(body, {}, ["bluesky"])
        assert any(r.check_name == "bluesky-length" for r in results)
        check = next(r for r in results if r.check_name == "bluesky-length")
        assert check.platform == "bluesky"
        assert "301" in check.message

    def test_bluesky_exactly_300_ok(self):
        body = "A" * 300
        results = check_platform_specific(body, {}, ["bluesky"])
        assert not any(r.check_name == "bluesky-length" for r in results)

    def test_mastodon_long_content(self):
        body = "A" * 501
        results = check_platform_specific(body, {}, ["mastodon"])
        assert any(r.check_name == "mastodon-length" for r in results)
        check = next(r for r in results if r.check_name == "mastodon-length")
        assert check.platform == "mastodon"

    def test_mastodon_exactly_500_ok(self):
        body = "A" * 500
        results = check_platform_specific(body, {}, ["mastodon"])
        assert not any(r.check_name == "mastodon-length" for r in results)

    def test_devto_canonical_missing(self):
        results = check_platform_specific("body", {}, ["devto"])
        assert any(r.check_name == "devto-canonical" for r in results)
        check = next(r for r in results if r.check_name == "devto-canonical")
        assert check.platform == "devto"

    def test_devto_canonical_present(self):
        fm = {"canonical_url": "https://example.com/post"}
        results = check_platform_specific("body", fm, ["devto"])
        assert not any(r.check_name == "devto-canonical" for r in results)

    def test_multiple_platforms(self):
        body = "A" * 600
        results = check_platform_specific(body, {}, ["bluesky", "mastodon", "devto"])
        assert any(r.check_name == "bluesky-length" for r in results)
        assert any(r.check_name == "mastodon-length" for r in results)
        assert any(r.check_name == "devto-canonical" for r in results)

    def test_unknown_platform_no_error(self):
        results = check_platform_specific("body", {}, ["unknown-platform"])
        # Should not crash, just no results for unknown platform
        assert len(results) == 0

    def test_disabled_platform_check(self):
        body = "A" * 301
        overrides = {"bluesky-length": "disabled"}
        results = check_platform_specific(body, {}, ["bluesky"], severity_overrides=overrides)
        assert not any(r.check_name == "bluesky-length" for r in results)


# ── check_file integration tests ────────────────────────


class TestCheckFile:
    def test_valid_file(self, tmp_path):
        fm = {
            "title": "Valid Article",
            "date": "2025-01-01",
            "tags": ["test"],
            "description": "A test article",
        }
        body = " ".join(["word"] * 100)
        md_file = _make_md(tmp_path, fm, body)

        report = check_file(md_file, site_base_url="https://example.com")
        assert report.passed

    def test_missing_title_file(self, tmp_path):
        md_file = _make_md(tmp_path, {"date": "2025-01-01"})
        report = check_file(md_file)
        assert not report.passed
        assert any(r.check_name == "missing-title" for r in report.results)

    def test_file_with_platforms(self, tmp_path):
        fm = {"title": "Test"}
        body = "A" * 301
        md_file = _make_md(tmp_path, fm, body)
        report = check_file(md_file, platforms=["bluesky"])
        assert any(r.check_name == "bluesky-length" for r in report.results)

    def test_file_with_severity_overrides(self, tmp_path):
        fm = {"title": "Test"}  # missing tags
        body = " ".join(["word"] * 100)
        md_file = _make_md(tmp_path, fm, body)

        overrides = {"missing-tags": "disabled", "missing-date": "disabled"}
        report = check_file(md_file, severity_overrides=overrides)
        assert not any(r.check_name == "missing-tags" for r in report.results)

    def test_unreadable_file(self, tmp_path):
        report = check_file(tmp_path / "nonexistent.md")
        assert not report.passed
        assert any(r.check_name == "file-read-error" for r in report.results)

    def test_binary_file(self, tmp_path):
        binary_file = tmp_path / "image.png"
        binary_file.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)
        report = check_file(binary_file)
        assert not report.passed
        assert any(r.check_name == "file-read-error" for r in report.results)
        assert "binary" in report.results[0].message.lower()

    def test_no_front_matter(self, tmp_path):
        md_file = _make_md_raw(tmp_path, "Just some plain text without front matter.")
        report = check_file(md_file)
        assert any(r.check_name == "missing-title" for r in report.results)

    def test_file_report_path(self, tmp_path):
        md_file = _make_md(tmp_path, {"title": "Test"})
        report = check_file(md_file)
        assert report.file == str(md_file)

    @patch("requests.head")
    def test_file_with_check_links(self, mock_head, tmp_path):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_head.return_value = mock_resp

        fm = {"title": "Test", "date": "2025-01-01", "tags": ["t"], "description": "d"}
        body = "See [broken](https://example.com/gone) for details."
        md_file = _make_md(tmp_path, fm, body)

        report = check_file(md_file, site_base_url="https://example.com", check_links=True)
        assert any(r.check_name == "broken-external-link" for r in report.results)
        mock_head.assert_called_once()


# ── External link check tests ───────────────────────────


class TestCheckExternalLinks:
    def test_no_links(self):
        results = check_external_links("No links here.")
        assert len(results) == 0

    @patch("requests.head")
    def test_valid_link(self, mock_head):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_head.return_value = mock_resp

        results = check_external_links("Check [this](https://example.com/ok)")
        assert len(results) == 0

    @patch("requests.head")
    def test_broken_link_404(self, mock_head):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_head.return_value = mock_resp

        results = check_external_links("Check [this](https://example.com/broken)")
        assert len(results) == 1
        assert results[0].check_name == "broken-external-link"
        assert "404" in results[0].message

    @patch("requests.head")
    def test_unreachable_link(self, mock_head):
        import requests as req
        mock_head.side_effect = req.ConnectionError("Connection refused")

        results = check_external_links("Check [this](https://example.com/down)")
        assert len(results) == 1
        assert "unreachable" in results[0].message.lower()

    @patch("requests.head")
    def test_deduplicates_urls(self, mock_head):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_head.return_value = mock_resp

        body = "[link1](https://example.com/page) and [link2](https://example.com/page)"
        check_external_links(body)
        # Should only check once
        assert mock_head.call_count == 1

    def test_disabled_check(self):
        overrides = {"broken-external-link": "disabled"}
        results = check_external_links(
            "[link](https://example.com/broken)",
            severity_overrides=overrides,
        )
        assert len(results) == 0


# ── CLI check command tests ──────────────────────────────


class TestCheckCLI:
    def test_check_passing_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fm = {
            "title": "Good Article",
            "date": "2025-01-01",
            "tags": ["test"],
            "description": "Desc",
        }
        body = " ".join(["word"] * 100)
        md_file = _make_md(tmp_path, fm, body)

        # Create .crier directory for local config
        (tmp_path / ".crier").mkdir(exist_ok=True)

        runner = CliRunner()
        result = runner.invoke(cli, ["check", str(md_file)])
        assert result.exit_code == 0

    def test_check_failing_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # No title = error
        md_file = _make_md_raw(tmp_path, "No front matter at all.")

        (tmp_path / ".crier").mkdir(exist_ok=True)

        runner = CliRunner()
        result = runner.invoke(cli, ["check", str(md_file)])
        assert result.exit_code == 1

    def test_check_json_output(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fm = {"title": "Test", "date": "2025-01-01", "tags": ["t"], "description": "d"}
        body = " ".join(["word"] * 100)
        md_file = _make_md(tmp_path, fm, body)

        (tmp_path / ".crier").mkdir(exist_ok=True)

        runner = CliRunner()
        result = runner.invoke(cli, ["check", str(md_file), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "reports" in data
        assert "summary" in data
        assert data["summary"]["files"] == 1
        assert data["summary"]["passed"] == 1

    def test_check_strict_mode(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Missing date is a warning by default, strict promotes to error
        fm = {"title": "Test", "tags": ["t"], "description": "d"}
        body = " ".join(["word"] * 100)
        md_file = _make_md(tmp_path, fm, body)

        (tmp_path / ".crier").mkdir(exist_ok=True)

        runner = CliRunner()
        result = runner.invoke(cli, ["check", str(md_file), "--strict"])
        # missing-date is now an error
        assert result.exit_code == 1

    def test_check_with_platform(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fm = {"title": "Test", "date": "2025-01-01", "tags": ["t"], "description": "d"}
        body = "A" * 301  # Over bluesky limit
        md_file = _make_md(tmp_path, fm, body)

        (tmp_path / ".crier").mkdir(exist_ok=True)

        runner = CliRunner()
        result = runner.invoke(cli, ["check", str(md_file), "--to", "bluesky", "--json"])
        data = json.loads(result.output)
        checks = data["reports"][0]["results"]
        check_names = [c["check"] for c in checks]
        assert "bluesky-length" in check_names

    def test_check_no_args_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".crier").mkdir(exist_ok=True)

        runner = CliRunner()
        result = runner.invoke(cli, ["check"])
        assert result.exit_code == 1

    def test_check_all_flag(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        # Set up content path
        content_dir = tmp_path / "content"
        content_dir.mkdir()

        fm = {"title": "Article One", "date": "2025-01-01", "tags": ["t"], "description": "d"}
        body = " ".join(["word"] * 100)
        _make_md(content_dir, fm, body)

        # Set up .crier config
        crier_dir = tmp_path / ".crier"
        crier_dir.mkdir(exist_ok=True)
        local_config = {"content_paths": [str(content_dir)], "file_extensions": [".md"]}
        (crier_dir / "config.yaml").write_text(yaml.dump(local_config))

        runner = CliRunner()
        result = runner.invoke(cli, ["check", "--all"])
        assert result.exit_code == 0

    def test_check_multiple_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".crier").mkdir(exist_ok=True)

        fm = {"title": "File One", "date": "2025-01-01", "tags": ["t"], "description": "d"}
        body = " ".join(["word"] * 100)

        file1 = tmp_path / "file1.md"
        file1.write_text(f"---\n{yaml.dump(fm)}---\n\n{body}\n")

        file2 = tmp_path / "file2.md"
        file2.write_text(f"---\n{yaml.dump(fm)}---\n\n{body}\n")

        runner = CliRunner()
        result = runner.invoke(cli, ["check", str(file1), str(file2)])
        assert result.exit_code == 0

    def test_check_partial_failure_exit_code_2(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".crier").mkdir(exist_ok=True)

        # File 1: good
        fm_good = {"title": "Good", "date": "2025-01-01", "tags": ["t"], "description": "d"}
        body = " ".join(["word"] * 100)
        file1 = tmp_path / "good.md"
        file1.write_text(f"---\n{yaml.dump(fm_good)}---\n\n{body}\n")

        # File 2: bad (no front matter = missing title error)
        file2 = tmp_path / "bad.md"
        file2.write_text("No front matter here.\n")

        runner = CliRunner()
        result = runner.invoke(cli, ["check", str(file1), str(file2)])
        assert result.exit_code == 2  # Partial failure


# ── Config override integration tests ────────────────────


class TestCheckConfigOverrides:
    def test_config_disables_check(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        # Write check overrides to the global config
        config_dir = tmp_path / "config"
        config_dir.mkdir(exist_ok=True)
        global_config = {
            "checks": {
                "missing-tags": "disabled",
                "missing-date": "disabled",
                "missing-description": "disabled",
            }
        }
        config_file = config_dir / "config.yaml"
        config_file.write_text(yaml.dump(global_config))
        monkeypatch.setattr("crier.config.DEFAULT_CONFIG_FILE", config_file)
        monkeypatch.setattr("crier.config.DEFAULT_CONFIG_DIR", config_dir)

        fm = {"title": "Test"}  # Missing tags, date, description
        body = " ".join(["word"] * 100)
        md_file = _make_md(tmp_path, fm, body)

        runner = CliRunner()
        result = runner.invoke(cli, ["check", str(md_file)])
        # All normally-problematic checks are disabled, should pass
        assert result.exit_code == 0

    def test_config_promotes_warning_to_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        # Write check overrides to the global config
        config_dir = tmp_path / "config"
        config_dir.mkdir(exist_ok=True)
        global_config = {"checks": {"missing-date": "error"}}
        config_file = config_dir / "config.yaml"
        config_file.write_text(yaml.dump(global_config))
        monkeypatch.setattr("crier.config.DEFAULT_CONFIG_FILE", config_file)
        monkeypatch.setattr("crier.config.DEFAULT_CONFIG_DIR", config_dir)

        fm = {"title": "Test", "tags": ["t"], "description": "d"}
        body = " ".join(["word"] * 100)
        md_file = _make_md(tmp_path, fm, body)

        runner = CliRunner()
        result = runner.invoke(cli, ["check", str(md_file), "--json"])
        data = json.loads(result.output)
        date_check = next(
            (c for c in data["reports"][0]["results"] if c["check"] == "missing-date"),
            None,
        )
        assert date_check is not None
        assert date_check["severity"] == "error"
        assert result.exit_code == 1


# ── Publish integration tests ────────────────────────────


class TestPublishCheckIntegration:
    def test_publish_blocks_on_check_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".crier").mkdir(exist_ok=True)

        # File with no title (error)
        md_file = tmp_path / "bad.md"
        md_file.write_text("No front matter.\n")

        monkeypatch.setenv("CRIER_DEVTO_API_KEY", "test-key")

        runner = CliRunner()
        result = runner.invoke(cli, ["publish", str(md_file), "--to", "devto"])
        assert result.exit_code == 1
        assert "check failed" in result.output.lower() or "missing-title" in result.output.lower()

    def test_publish_no_check_skips_validation(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".crier").mkdir(exist_ok=True)

        # File with no title (would normally error)
        md_file = tmp_path / "bad.md"
        md_file.write_text("---\ntitle: ''\n---\n\nBody content.\n")

        monkeypatch.setenv("CRIER_DEVTO_API_KEY", "test-key")

        runner = CliRunner()
        # --no-check should skip validation; the publish will fail for other reasons
        # (no platform API), but it should not fail due to the check
        result = runner.invoke(cli, ["publish", str(md_file), "--to", "devto", "--no-check", "--dry-run"])
        # Should not mention "check failed"
        assert "check failed" not in result.output.lower()

    def test_publish_strict_blocks_on_warning(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".crier").mkdir(exist_ok=True)

        # File with title but missing date (warning, promoted to error in strict)
        fm = {"title": "Test Article"}
        body = " ".join(["word"] * 100)
        md_file = _make_md(tmp_path, fm, body)

        monkeypatch.setenv("CRIER_DEVTO_API_KEY", "test-key")

        runner = CliRunner()
        result = runner.invoke(cli, ["publish", str(md_file), "--to", "devto", "--strict"])
        assert result.exit_code == 1


# ── Audit check integration tests ───────────────────────


class TestAuditCheckIntegration:
    """Test that --check flag in audit skips files that fail validation."""

    # These tests are lightweight — they just verify the flag is accepted
    # and integrated. Full audit flow requires more setup.

    def test_audit_check_flag_accepted(self, tmp_path, monkeypatch):
        """Verify --check flag doesn't cause an error."""
        monkeypatch.chdir(tmp_path)
        crier_dir = tmp_path / ".crier"
        crier_dir.mkdir(exist_ok=True)
        (crier_dir / "config.yaml").write_text(yaml.dump({
            "content_paths": [str(tmp_path)],
            "file_extensions": [".md"],
        }))
        (crier_dir / "registry.yaml").write_text("version: 2\narticles: {}\n")

        # Create a valid file
        fm = {"title": "Test", "date": "2025-01-01", "tags": ["t"], "description": "d"}
        body = " ".join(["word"] * 100)
        _make_md(tmp_path, fm, body)

        monkeypatch.setenv("CRIER_DEVTO_API_KEY", "test-key")

        runner = CliRunner()
        # --check should be accepted without error
        result = runner.invoke(cli, ["audit", "--check", "--to", "devto"])
        # Should not crash with "no such option"
        assert "no such option" not in result.output.lower()
