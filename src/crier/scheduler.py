"""Content scheduling for crier.

This module provides scheduling functionality for delayed publishing:
- ScheduledPost dataclass to represent scheduled posts
- schedule.yaml storage for persistence
- Time parsing with natural language support (via dateparser)
- Cron-friendly run command for processing due schedules
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid
import yaml


@dataclass
class ScheduledPost:
    """Represents a scheduled publish operation."""

    id: str
    file_path: str
    platform: str
    scheduled_time: datetime
    created_at: datetime
    status: str  # pending, published, failed, cancelled
    error: str | None = None
    rewrite: str | None = None
    auto_rewrite: bool = False
    profile: str | None = None  # Profile to use instead of single platform

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "id": self.id,
            "file_path": self.file_path,
            "platform": self.platform,
            "scheduled_time": self.scheduled_time.isoformat(),
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "error": self.error,
            "rewrite": self.rewrite,
            "auto_rewrite": self.auto_rewrite,
            "profile": self.profile,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScheduledPost":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            file_path=data["file_path"],
            platform=data["platform"],
            scheduled_time=datetime.fromisoformat(data["scheduled_time"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            status=data["status"],
            error=data.get("error"),
            rewrite=data.get("rewrite"),
            auto_rewrite=data.get("auto_rewrite", False),
            profile=data.get("profile"),
        )


def get_schedule_path(base_path: Path | None = None) -> Path:
    """Get the schedule.yaml file path."""
    if base_path is None:
        base_path = Path.cwd()
    return base_path / ".crier" / "schedule.yaml"


def load_schedule(base_path: Path | None = None) -> dict[str, Any]:
    """Load the schedule from disk."""
    schedule_file = get_schedule_path(base_path)

    if not schedule_file.exists():
        return {"version": 1, "scheduled_posts": []}

    with open(schedule_file) as f:
        data = yaml.safe_load(f) or {}

    return data


def save_schedule(schedule: dict[str, Any], base_path: Path | None = None) -> None:
    """Save the schedule to disk."""
    schedule_file = get_schedule_path(base_path)
    schedule_file.parent.mkdir(parents=True, exist_ok=True)

    with open(schedule_file, "w") as f:
        yaml.safe_dump(schedule, f, default_flow_style=False, sort_keys=False)


def create_scheduled_post(
    file_path: str,
    platform: str,
    scheduled_time: datetime,
    rewrite: str | None = None,
    auto_rewrite: bool = False,
    profile: str | None = None,
    base_path: Path | None = None,
) -> ScheduledPost:
    """Create and save a new scheduled post.

    Args:
        file_path: Path to the markdown file
        platform: Platform name (or empty string if using profile)
        scheduled_time: When to publish (should be UTC)
        rewrite: Optional custom rewrite content
        auto_rewrite: Whether to use LLM auto-rewrite
        profile: Optional profile name to use instead of platform
        base_path: Base path for schedule storage

    Returns:
        The created ScheduledPost
    """
    # Ensure scheduled_time is in UTC
    if scheduled_time.tzinfo is None:
        scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)

    post = ScheduledPost(
        id=str(uuid.uuid4())[:8],
        file_path=str(file_path),
        platform=platform,
        scheduled_time=scheduled_time,
        created_at=datetime.now(timezone.utc),
        status="pending",
        rewrite=rewrite,
        auto_rewrite=auto_rewrite,
        profile=profile,
    )

    schedule = load_schedule(base_path)
    schedule["scheduled_posts"].append(post.to_dict())
    save_schedule(schedule, base_path)

    return post


def get_scheduled_post(post_id: str, base_path: Path | None = None) -> ScheduledPost | None:
    """Get a scheduled post by ID."""
    schedule = load_schedule(base_path)

    for post_data in schedule.get("scheduled_posts", []):
        if post_data["id"] == post_id or post_data["id"].startswith(post_id):
            return ScheduledPost.from_dict(post_data)

    return None


def list_scheduled_posts(
    status: str | None = None,
    base_path: Path | None = None,
) -> list[ScheduledPost]:
    """List scheduled posts, optionally filtered by status.

    Args:
        status: Filter by status (pending, published, failed, cancelled)
        base_path: Base path for schedule storage

    Returns:
        List of ScheduledPost objects
    """
    schedule = load_schedule(base_path)
    posts = []

    for post_data in schedule.get("scheduled_posts", []):
        if status is None or post_data["status"] == status:
            posts.append(ScheduledPost.from_dict(post_data))

    # Sort by scheduled_time
    posts.sort(key=lambda p: p.scheduled_time)
    return posts


def get_due_posts(base_path: Path | None = None) -> list[ScheduledPost]:
    """Get all pending posts that are due for publishing.

    Returns posts where:
    - status == "pending"
    - scheduled_time <= now

    Returns:
        List of due ScheduledPost objects
    """
    now = datetime.now(timezone.utc)
    posts = list_scheduled_posts(status="pending", base_path=base_path)

    return [p for p in posts if p.scheduled_time <= now]


def update_scheduled_post(
    post_id: str,
    status: str | None = None,
    error: str | None = None,
    base_path: Path | None = None,
) -> bool:
    """Update a scheduled post's status.

    Args:
        post_id: Post ID (or prefix)
        status: New status
        error: Error message (for failed status)
        base_path: Base path for schedule storage

    Returns:
        True if updated, False if not found
    """
    schedule = load_schedule(base_path)

    for post_data in schedule.get("scheduled_posts", []):
        if post_data["id"] == post_id or post_data["id"].startswith(post_id):
            if status:
                post_data["status"] = status
            if error is not None:
                post_data["error"] = error
            save_schedule(schedule, base_path)
            return True

    return False


def cancel_scheduled_post(post_id: str, base_path: Path | None = None) -> bool:
    """Cancel a scheduled post.

    Args:
        post_id: Post ID (or prefix)
        base_path: Base path for schedule storage

    Returns:
        True if cancelled, False if not found or not pending
    """
    schedule = load_schedule(base_path)

    for post_data in schedule.get("scheduled_posts", []):
        if post_data["id"] == post_id or post_data["id"].startswith(post_id):
            if post_data["status"] != "pending":
                return False
            post_data["status"] = "cancelled"
            save_schedule(schedule, base_path)
            return True

    return False


def delete_scheduled_post(post_id: str, base_path: Path | None = None) -> bool:
    """Delete a scheduled post from the schedule.

    Args:
        post_id: Post ID (or prefix)
        base_path: Base path for schedule storage

    Returns:
        True if deleted, False if not found
    """
    schedule = load_schedule(base_path)
    original_count = len(schedule.get("scheduled_posts", []))

    schedule["scheduled_posts"] = [
        p for p in schedule.get("scheduled_posts", [])
        if not (p["id"] == post_id or p["id"].startswith(post_id))
    ]

    if len(schedule["scheduled_posts"]) < original_count:
        save_schedule(schedule, base_path)
        return True

    return False


def parse_schedule_time(time_str: str) -> datetime | None:
    """Parse a schedule time string into a datetime.

    Supports:
    - ISO format: "2025-01-24 09:00" or "2025-01-24T09:00:00"
    - Natural language: "tomorrow 9am", "in 2 hours", "next monday 10am"

    The dateparser library is used for natural language parsing.
    All times are converted to UTC.

    Args:
        time_str: Time string to parse

    Returns:
        datetime in UTC, or None if parsing failed
    """
    try:
        import dateparser
    except ImportError:
        # Fall back to basic ISO parsing if dateparser not installed
        try:
            dt = datetime.fromisoformat(time_str)
            if dt.tzinfo is None:
                # Assume local time, convert to UTC
                from datetime import timezone as tz
                dt = dt.replace(tzinfo=tz.utc)
            return dt
        except ValueError:
            return None

    # Use dateparser for natural language
    settings = {
        "PREFER_DATES_FROM": "future",
        "RETURN_AS_TIMEZONE_AWARE": True,
        "TIMEZONE": "UTC",
    }

    parsed = dateparser.parse(time_str, settings=settings)

    if parsed:
        # Ensure UTC
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)

    return parsed


def cleanup_old_posts(days: int = 30, base_path: Path | None = None) -> int:
    """Remove old completed/cancelled posts from schedule.

    Args:
        days: Remove posts older than this many days
        base_path: Base path for schedule storage

    Returns:
        Number of posts removed
    """
    schedule = load_schedule(base_path)
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 24 * 60 * 60)
    original_count = len(schedule.get("scheduled_posts", []))

    schedule["scheduled_posts"] = [
        p for p in schedule.get("scheduled_posts", [])
        if p["status"] == "pending" or
        datetime.fromisoformat(p["scheduled_time"]).timestamp() > cutoff
    ]

    removed = original_count - len(schedule["scheduled_posts"])
    if removed > 0:
        save_schedule(schedule, base_path)

    return removed
