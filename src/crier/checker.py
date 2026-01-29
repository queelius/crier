"""Pre-publish content validation for crier."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .converters.markdown import parse_front_matter


@dataclass
class CheckResult:
    """A single validation finding."""

    severity: str  # "error", "warning", "info"
    check_name: str  # e.g. "missing-title", "broken-link"
    message: str  # Human-readable description
    line: int | None = None  # Line number if applicable
    platform: str | None = None  # Platform-specific check, or None for general


@dataclass
class CheckReport:
    """Validation report for a single file."""

    file: str
    results: list[CheckResult] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(r.severity == "error" for r in self.results)

    @property
    def has_warnings(self) -> bool:
        return any(r.severity == "warning" for r in self.results)

    @property
    def passed(self) -> bool:
        """No errors found (warnings/info are acceptable)."""
        return not self.has_errors

    def with_elevated_warnings(self) -> CheckReport:
        """Return new report with warnings promoted to errors (for --strict mode)."""
        return CheckReport(
            file=self.file,
            results=[
                CheckResult(
                    severity="error" if r.severity == "warning" else r.severity,
                    check_name=r.check_name,
                    message=r.message,
                    line=r.line,
                    platform=r.platform,
                )
                for r in self.results
            ],
        )


# Default severities for each check
DEFAULT_SEVERITIES: dict[str, str] = {
    # Front matter checks
    "missing-title": "error",
    "missing-date": "warning",
    "future-date": "info",
    "missing-tags": "warning",
    "empty-tags": "warning",
    "title-length": "warning",
    "missing-description": "info",
    # Content checks
    "empty-body": "error",
    "short-body": "warning",
    "broken-relative-links": "warning",
    "image-alt-text": "info",
    # Platform-specific checks
    "bluesky-length": "warning",
    "mastodon-length": "warning",
    "devto-canonical": "info",
    # External link checks
    "broken-external-link": "warning",
}


def get_effective_severity(check_name: str, config_overrides: dict[str, str] | None = None) -> str | None:
    """Get the effective severity for a check, considering config overrides.

    Returns None if the check is disabled.
    """
    if config_overrides and check_name in config_overrides:
        override = config_overrides[check_name]
        if override == "disabled":
            return None
        return override
    return DEFAULT_SEVERITIES.get(check_name)


def check_front_matter(
    front_matter: dict[str, Any],
    severity_overrides: dict[str, str] | None = None,
) -> list[CheckResult]:
    """Validate front matter fields."""
    results: list[CheckResult] = []

    # missing-title
    sev = get_effective_severity("missing-title", severity_overrides)
    if sev and not front_matter.get("title"):
        results.append(CheckResult(
            severity=sev,
            check_name="missing-title",
            message="No 'title' in front matter",
        ))

    # missing-date
    sev = get_effective_severity("missing-date", severity_overrides)
    if sev and not front_matter.get("date"):
        results.append(CheckResult(
            severity=sev,
            check_name="missing-date",
            message="No 'date' in front matter",
        ))

    # future-date
    sev = get_effective_severity("future-date", severity_overrides)
    if sev and front_matter.get("date"):
        raw_date = front_matter["date"]
        try:
            if isinstance(raw_date, datetime):
                dt = raw_date.date()
            elif isinstance(raw_date, date):
                dt = raw_date
            elif isinstance(raw_date, str):
                # Try common formats
                for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
                    try:
                        dt = datetime.strptime(raw_date, fmt).date()
                        break
                    except ValueError:
                        continue
                else:
                    dt = None
            else:
                dt = None

            if dt and dt > date.today():
                results.append(CheckResult(
                    severity=sev,
                    check_name="future-date",
                    message=f"Date is in the future ({dt})",
                ))
        except (ValueError, TypeError):
            pass  # Can't parse date, skip check

    # missing-tags
    sev = get_effective_severity("missing-tags", severity_overrides)
    if sev and "tags" not in front_matter:
        results.append(CheckResult(
            severity=sev,
            check_name="missing-tags",
            message="No 'tags' in front matter",
        ))

    # empty-tags
    sev = get_effective_severity("empty-tags", severity_overrides)
    if sev and "tags" in front_matter:
        tags = front_matter["tags"]
        if isinstance(tags, list) and not tags:
            results.append(CheckResult(
                severity=sev,
                check_name="empty-tags",
                message="Tags field is empty",
            ))

    # title-length
    sev = get_effective_severity("title-length", severity_overrides)
    if sev and front_matter.get("title"):
        title = str(front_matter["title"])
        if len(title) > 100:
            results.append(CheckResult(
                severity=sev,
                check_name="title-length",
                message=f"Title exceeds 100 characters ({len(title)} chars)",
            ))

    # missing-description
    sev = get_effective_severity("missing-description", severity_overrides)
    if sev:
        has_desc = front_matter.get("description") or front_matter.get("excerpt")
        if not has_desc:
            results.append(CheckResult(
                severity=sev,
                check_name="missing-description",
                message="No 'description' or 'excerpt' in front matter",
            ))

    return results


def check_content(
    body: str,
    severity_overrides: dict[str, str] | None = None,
    site_base_url: str | None = None,
) -> list[CheckResult]:
    """Validate article body content."""
    results: list[CheckResult] = []

    # empty-body
    sev = get_effective_severity("empty-body", severity_overrides)
    if sev and not body.strip():
        results.append(CheckResult(
            severity=sev,
            check_name="empty-body",
            message="Body is empty or whitespace-only",
        ))
        return results  # No point checking more

    # short-body
    sev = get_effective_severity("short-body", severity_overrides)
    if sev:
        word_count = len(body.split())
        if word_count < 50:
            results.append(CheckResult(
                severity=sev,
                check_name="short-body",
                message=f"Body has only {word_count} words (under 50)",
            ))

    # broken-relative-links: relative links without site_base_url
    sev = get_effective_severity("broken-relative-links", severity_overrides)
    if sev and not site_base_url:
        # Find markdown relative links: [text](/path) or [text](./path) or [text](../path)
        md_link_pattern = r'!?\[[^\]]*\]\(([^)]+)\)'
        for match in re.finditer(md_link_pattern, body):
            url = match.group(1).strip()
            # Check if relative (starts with / or ./ or ../ but not http/https/# etc)
            if url and not url.startswith(("http://", "https://", "//", "#", "mailto:", "tel:", "data:")):
                line_num = body[:match.start()].count('\n') + 1
                results.append(CheckResult(
                    severity=sev,
                    check_name="broken-relative-links",
                    message=f"Relative link '{url}' may not resolve (no site_base_url configured)",
                    line=line_num,
                ))

    # image-alt-text: images missing alt text
    sev = get_effective_severity("image-alt-text", severity_overrides)
    if sev:
        # Match ![](url) - empty alt text
        img_pattern = r'!\[\s*\]\([^)]+\)'
        for match in re.finditer(img_pattern, body):
            line_num = body[:match.start()].count('\n') + 1
            results.append(CheckResult(
                severity=sev,
                check_name="image-alt-text",
                message="Image missing alt text",
                line=line_num,
            ))

    return results


def check_platform_specific(
    body: str,
    front_matter: dict[str, Any],
    platforms: list[str],
    severity_overrides: dict[str, str] | None = None,
) -> list[CheckResult]:
    """Run platform-specific validation checks."""
    results: list[CheckResult] = []

    for platform in platforms:
        if platform == "bluesky":
            sev = get_effective_severity("bluesky-length", severity_overrides)
            if sev and len(body) > 300:
                results.append(CheckResult(
                    severity=sev,
                    check_name="bluesky-length",
                    message=f"Content exceeds Bluesky's 300 char limit ({len(body)} chars) — consider --rewrite, --auto-rewrite, or --thread",
                    platform="bluesky",
                ))

        elif platform == "mastodon":
            sev = get_effective_severity("mastodon-length", severity_overrides)
            if sev and len(body) > 500:
                results.append(CheckResult(
                    severity=sev,
                    check_name="mastodon-length",
                    message=f"Content exceeds Mastodon's 500 char limit ({len(body)} chars) — consider --rewrite, --auto-rewrite, or --thread",
                    platform="mastodon",
                ))

        elif platform == "devto":
            sev = get_effective_severity("devto-canonical", severity_overrides)
            if sev and not front_matter.get("canonical_url"):
                results.append(CheckResult(
                    severity=sev,
                    check_name="devto-canonical",
                    message="No canonical_url — Dev.to won't link back to your original post",
                    platform="devto",
                ))

    return results


def check_external_links(
    body: str,
    severity_overrides: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> list[CheckResult]:
    """Check external links for broken URLs using HEAD requests.

    Sequential with a small delay between requests to avoid triggering
    rate limits on target servers. Line numbers refer to position within
    the body (after front matter), not the full file.
    """
    import time
    import requests

    results: list[CheckResult] = []
    sev = get_effective_severity("broken-external-link", severity_overrides)
    if not sev:
        return results

    # Extract all external URLs from markdown links and HTML
    url_patterns = [
        r'!?\[[^\]]*\]\((https?://[^)]+)\)',  # markdown links/images
        r'href=["\']?(https?://[^"\'>\s]+)',   # HTML href
        r'src=["\']?(https?://[^"\'>\s]+)',    # HTML src
    ]

    urls_seen: set[str] = set()
    for pattern in url_patterns:
        for match in re.finditer(pattern, body):
            url = match.group(1).strip()
            urls_seen.add(url)

    def _find_line(url: str) -> int | None:
        idx = body.find(url)
        return body[:idx].count('\n') + 1 if idx >= 0 else None

    headers = {"User-Agent": "crier-link-checker/1.0"}

    for i, url in enumerate(urls_seen):
        if i > 0:
            time.sleep(0.1)  # Rate limit: 100ms between requests
        try:
            resp = requests.head(url, timeout=timeout, allow_redirects=True, headers=headers)
            if resp.status_code >= 400:
                results.append(CheckResult(
                    severity=sev,
                    check_name="broken-external-link",
                    message=f"URL returned {resp.status_code}: {url}",
                    line=_find_line(url),
                ))
        except requests.RequestException as e:
            results.append(CheckResult(
                severity=sev,
                check_name="broken-external-link",
                message=f"URL unreachable: {url} ({e.__class__.__name__})",
                line=_find_line(url),
            ))

    return results


def check_article(
    front_matter: dict[str, Any],
    body: str,
    platforms: list[str] | None = None,
    severity_overrides: dict[str, str] | None = None,
    site_base_url: str | None = None,
    check_links: bool = False,
) -> list[CheckResult]:
    """Run all checks on parsed article content (pure function, no I/O).

    Args:
        front_matter: Parsed YAML front matter dict
        body: Article body content
        platforms: Optional list of target platforms for platform-specific checks
        severity_overrides: Dict of check_name -> severity from config
        site_base_url: Site base URL for relative link validation
        check_links: Whether to check external links (slow, opt-in)

    Returns:
        List of CheckResult findings
    """
    results: list[CheckResult] = []
    results.extend(check_front_matter(front_matter, severity_overrides))
    results.extend(check_content(body, severity_overrides, site_base_url))

    if platforms:
        results.extend(
            check_platform_specific(body, front_matter, platforms, severity_overrides)
        )

    if check_links:
        results.extend(check_external_links(body, severity_overrides))

    return results


def check_file(
    file_path: str | Path,
    platforms: list[str] | None = None,
    severity_overrides: dict[str, str] | None = None,
    site_base_url: str | None = None,
    check_links: bool = False,
) -> CheckReport:
    """Run all checks on a markdown file (I/O wrapper around check_article).

    Args:
        file_path: Path to the markdown file
        platforms: Optional list of target platforms for platform-specific checks
        severity_overrides: Dict of check_name -> severity from config
        site_base_url: Site base URL for relative link validation
        check_links: Whether to check external links (slow, opt-in)

    Returns:
        CheckReport with all findings
    """
    file_path = Path(file_path)

    try:
        content = file_path.read_text()
    except UnicodeDecodeError:
        return CheckReport(
            file=str(file_path),
            results=[CheckResult(
                severity="error",
                check_name="file-read-error",
                message="Not a text file (binary content)",
            )],
        )
    except OSError as e:
        return CheckReport(
            file=str(file_path),
            results=[CheckResult(
                severity="error",
                check_name="file-read-error",
                message=f"Cannot read file: {e}",
            )],
        )

    front_matter, body = parse_front_matter(content)

    results = check_article(
        front_matter, body, platforms, severity_overrides, site_base_url, check_links
    )

    return CheckReport(file=str(file_path), results=results)
