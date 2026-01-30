"""Shared utility functions for crier.

Pure functions extracted from cli.py — no CLI or I/O framework dependencies.
"""

import fnmatch
import re
from datetime import datetime, timedelta
from pathlib import Path


def truncate_at_sentence(text: str, max_chars: int) -> str:
    """Truncate text at sentence boundary, ensuring it fits within max_chars.

    Tries to cut at sentence boundary (., ?, !), then word boundary, then hard truncate.
    """
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]

    # Find last sentence boundary
    last_period = truncated.rfind('.')
    last_question = truncated.rfind('?')
    last_exclaim = truncated.rfind('!')
    last_sentence = max(last_period, last_question, last_exclaim)

    # Only use sentence boundary if it's in reasonable range (>50% of limit)
    if last_sentence > max_chars // 2:
        return truncated[:last_sentence + 1]

    # Fall back to word boundary
    last_space = truncated.rfind(' ')
    if last_space > max_chars // 2:
        return truncated[:last_space] + "..."

    # Last resort: hard truncate
    return truncated[:max_chars - 3] + "..."


def has_valid_front_matter(file_path: Path) -> bool:
    """Check if a file has valid front matter with a title."""
    from .converters import parse_markdown_file

    try:
        article = parse_markdown_file(str(file_path))
        return bool(article.title)
    except Exception:
        return False


def is_in_content_paths(file_path: Path) -> bool:
    """Check if a file is within configured content_paths."""
    from .config import get_content_paths

    content_paths = get_content_paths()
    if not content_paths:
        return False

    file_resolved = file_path.resolve()
    for content_path in content_paths:
        path_obj = Path(content_path).resolve()
        try:
            file_resolved.relative_to(path_obj)
            return True
        except ValueError:
            continue
    return False


def matches_exclude_pattern(filename: str, patterns: list[str]) -> bool:
    """Check if a filename matches any exclude pattern.

    Supports simple patterns:
    - Exact match: "_index.md"
    - Prefix wildcard: "draft-*" matches "draft-foo.md"
    - Suffix wildcard: "*.draft.md" matches "foo.draft.md"
    """
    for pattern in patterns:
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False


def parse_date_filter(value: str) -> datetime:
    """Parse relative (1d, 1w, 1m) or absolute (2025-01-01) date.

    Relative formats:
    - Nd = N days ago (e.g., 7d)
    - Nw = N weeks ago (e.g., 2w)
    - Nm = N months ago (e.g., 1m)
    - Ny = N years ago (e.g., 1y)

    Absolute formats:
    - YYYY-MM-DD (e.g., 2025-01-01)
    - Full ISO format (e.g., 2025-01-01T12:00:00)

    Raises:
        ValueError: If the date format is invalid.
    """
    # Try relative format: Nd, Nw, Nm, Ny
    match = re.match(r'^(\d+)([dwmy])$', value.lower())
    if match:
        n, unit = int(match.group(1)), match.group(2)
        now = datetime.now()
        if unit == 'd':
            return now - timedelta(days=n)
        elif unit == 'w':
            return now - timedelta(weeks=n)
        elif unit == 'm':
            return now - timedelta(days=n * 30)  # Approximate
        elif unit == 'y':
            return now - timedelta(days=n * 365)  # Approximate

    # Try absolute format: YYYY-MM-DD or full ISO
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(
            f"Invalid date format: '{value}'. "
            "Use relative (1d, 1w, 1m, 1y) or absolute (YYYY-MM-DD)."
        )


def get_content_date(file_path: Path) -> datetime | None:
    """Get date from front matter of a markdown file.

    Returns None if no date field or file can't be parsed.
    """
    try:
        with open(file_path) as f:
            content = f.read()

        # Check for YAML front matter
        if not content.startswith('---'):
            return None

        # Find end of front matter
        end_idx = content.find('---', 3)
        if end_idx == -1:
            return None

        front_matter = content[3:end_idx]

        # Parse YAML
        import yaml
        data = yaml.safe_load(front_matter)
        if not data or 'date' not in data:
            return None

        date_val = data['date']

        # Handle datetime objects (YAML parses dates automatically)
        if isinstance(date_val, datetime):
            return date_val
        if hasattr(date_val, 'year'):  # date object
            return datetime(date_val.year, date_val.month, date_val.day)

        # Handle string dates
        if isinstance(date_val, str):
            return datetime.fromisoformat(
                date_val.replace('Z', '+00:00')
            )

        return None
    except Exception:
        return None


def get_content_tags(file_path: Path) -> list[str]:
    """Get tags from front matter of a markdown file.

    Returns empty list if no tags field or file can't be parsed.
    Tags are normalized to lowercase for case-insensitive matching.
    """
    try:
        with open(file_path) as f:
            content = f.read()

        # Check for YAML front matter
        if not content.startswith('---'):
            return []

        # Find end of front matter
        end_idx = content.find('---', 3)
        if end_idx == -1:
            return []

        front_matter = content[3:end_idx]

        # Parse YAML
        import yaml
        data = yaml.safe_load(front_matter)
        if not data or 'tags' not in data:
            return []

        raw_tags = data['tags']

        # Handle list format: tags: [python, testing]
        if isinstance(raw_tags, list):
            return [str(t).lower().strip() for t in raw_tags if t]

        # Handle string format: tags: "python, testing"
        if isinstance(raw_tags, str):
            return [
                t.lower().strip() for t in raw_tags.split(',') if t.strip()
            ]

        return []
    except Exception:
        return []


def find_content_files(explicit_path: str | None = None) -> list[Path]:
    """Find content files to process.

    Args:
        explicit_path: If provided, scan this path. Otherwise use
            content_paths config.

    Returns:
        List of Path objects for files with valid front matter.

    Note:
        Excludes files matching exclude_patterns config
        (default: ["_index.md"]).
        Uses file_extensions config (default: [".md"]) for which
        files to scan.
    """
    from .config import (
        get_content_paths, get_exclude_patterns,
        get_file_extensions, DEFAULT_FILE_EXTENSIONS,
    )

    files: list[Path] = []

    # Get configured extensions, fallback to .md for backwards compat
    extensions = get_file_extensions() or DEFAULT_FILE_EXTENSIONS

    if explicit_path:
        # Explicit path provided - use it
        path_obj = Path(explicit_path)
        if path_obj.is_file():
            files = [path_obj]
        else:
            for ext in extensions:
                files.extend(path_obj.glob(f"**/*{ext}"))
    else:
        # Use configured content_paths
        content_paths = get_content_paths()
        if not content_paths:
            return []

        for content_path in content_paths:
            path_obj = Path(content_path)
            if path_obj.is_file():
                files.append(path_obj)
            elif path_obj.is_dir():
                for ext in extensions:
                    files.extend(path_obj.glob(f"**/*{ext}"))

    # Apply exclude patterns (default: ["_index.md"] for Hugo sections)
    exclude_patterns = get_exclude_patterns()
    if exclude_patterns:
        files = [
            f for f in files
            if not matches_exclude_pattern(f.name, exclude_patterns)
        ]

    # Filter to only files with valid front matter
    valid_files = [f for f in files if has_valid_front_matter(f)]
    return valid_files
