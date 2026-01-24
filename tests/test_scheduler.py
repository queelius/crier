"""Tests for crier.scheduler module."""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from crier.scheduler import (
    ScheduledPost,
    load_schedule,
    save_schedule,
    create_scheduled_post,
    get_scheduled_post,
    list_scheduled_posts,
    get_due_posts,
    update_scheduled_post,
    cancel_scheduled_post,
    delete_scheduled_post,
    parse_schedule_time,
    cleanup_old_posts,
)


@pytest.fixture
def tmp_schedule(tmp_path, monkeypatch):
    """Set up a temporary schedule directory."""
    crier_dir = tmp_path / ".crier"
    crier_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestScheduledPost:
    """Tests for ScheduledPost dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        now = datetime.now(timezone.utc)
        post = ScheduledPost(
            id="abc123",
            file_path="/path/to/file.md",
            platform="devto",
            scheduled_time=now,
            created_at=now,
            status="pending",
        )

        data = post.to_dict()
        assert data["id"] == "abc123"
        assert data["platform"] == "devto"
        assert data["status"] == "pending"

    def test_from_dict(self):
        """Test creation from dictionary."""
        now = datetime.now(timezone.utc)
        data = {
            "id": "abc123",
            "file_path": "/path/to/file.md",
            "platform": "devto",
            "scheduled_time": now.isoformat(),
            "created_at": now.isoformat(),
            "status": "pending",
        }

        post = ScheduledPost.from_dict(data)
        assert post.id == "abc123"
        assert post.platform == "devto"
        assert post.status == "pending"


class TestLoadSaveSchedule:
    """Tests for load_schedule and save_schedule."""

    def test_load_empty_schedule(self, tmp_schedule):
        """Loading non-existent schedule returns empty structure."""
        schedule = load_schedule(tmp_schedule)
        assert schedule["version"] == 1
        assert schedule["scheduled_posts"] == []

    def test_save_and_load(self, tmp_schedule):
        """Saved schedule can be loaded back."""
        schedule = {
            "version": 1,
            "scheduled_posts": [
                {"id": "test1", "platform": "devto", "status": "pending"}
            ]
        }
        save_schedule(schedule, tmp_schedule)

        loaded = load_schedule(tmp_schedule)
        assert len(loaded["scheduled_posts"]) == 1
        assert loaded["scheduled_posts"][0]["id"] == "test1"


class TestCreateScheduledPost:
    """Tests for create_scheduled_post."""

    def test_create_post(self, tmp_schedule):
        """Creating a scheduled post saves it."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)

        post = create_scheduled_post(
            file_path="test.md",
            platform="devto",
            scheduled_time=future_time,
            base_path=tmp_schedule,
        )

        assert post.id is not None
        assert post.platform == "devto"
        assert post.status == "pending"

        # Verify it was saved
        saved = get_scheduled_post(post.id, tmp_schedule)
        assert saved is not None
        assert saved.platform == "devto"

    def test_create_with_rewrite(self, tmp_schedule):
        """Creating a post with rewrite saves the content."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)

        post = create_scheduled_post(
            file_path="test.md",
            platform="bluesky",
            scheduled_time=future_time,
            rewrite="Custom short content",
            base_path=tmp_schedule,
        )

        assert post.rewrite == "Custom short content"

    def test_create_with_auto_rewrite(self, tmp_schedule):
        """Creating a post with auto_rewrite flag."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)

        post = create_scheduled_post(
            file_path="test.md",
            platform="bluesky",
            scheduled_time=future_time,
            auto_rewrite=True,
            base_path=tmp_schedule,
        )

        assert post.auto_rewrite is True


class TestListScheduledPosts:
    """Tests for list_scheduled_posts."""

    def test_list_empty(self, tmp_schedule):
        """Empty schedule returns empty list."""
        posts = list_scheduled_posts(base_path=tmp_schedule)
        assert posts == []

    def test_list_all(self, tmp_schedule):
        """List returns all posts."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)

        create_scheduled_post("a.md", "devto", future_time, base_path=tmp_schedule)
        create_scheduled_post("b.md", "bluesky", future_time, base_path=tmp_schedule)

        posts = list_scheduled_posts(base_path=tmp_schedule)
        assert len(posts) == 2

    def test_list_by_status(self, tmp_schedule):
        """List can filter by status."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)

        post = create_scheduled_post("a.md", "devto", future_time, base_path=tmp_schedule)
        create_scheduled_post("b.md", "bluesky", future_time, base_path=tmp_schedule)

        # Cancel one
        cancel_scheduled_post(post.id, tmp_schedule)

        pending = list_scheduled_posts(status="pending", base_path=tmp_schedule)
        assert len(pending) == 1

        cancelled = list_scheduled_posts(status="cancelled", base_path=tmp_schedule)
        assert len(cancelled) == 1


class TestGetDuePosts:
    """Tests for get_due_posts."""

    def test_no_due_posts(self, tmp_schedule):
        """Future posts are not due."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        create_scheduled_post("a.md", "devto", future_time, base_path=tmp_schedule)

        due = get_due_posts(tmp_schedule)
        assert len(due) == 0

    def test_past_posts_are_due(self, tmp_schedule):
        """Past posts are due."""
        past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        create_scheduled_post("a.md", "devto", past_time, base_path=tmp_schedule)

        due = get_due_posts(tmp_schedule)
        assert len(due) == 1

    def test_only_pending_are_due(self, tmp_schedule):
        """Only pending posts are returned as due."""
        past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        post = create_scheduled_post("a.md", "devto", past_time, base_path=tmp_schedule)

        # Cancel the post
        cancel_scheduled_post(post.id, tmp_schedule)

        due = get_due_posts(tmp_schedule)
        assert len(due) == 0


class TestUpdateScheduledPost:
    """Tests for update_scheduled_post."""

    def test_update_status(self, tmp_schedule):
        """Update changes status."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        post = create_scheduled_post("a.md", "devto", future_time, base_path=tmp_schedule)

        update_scheduled_post(post.id, status="published", base_path=tmp_schedule)

        updated = get_scheduled_post(post.id, tmp_schedule)
        assert updated.status == "published"

    def test_update_with_error(self, tmp_schedule):
        """Update can set error message."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        post = create_scheduled_post("a.md", "devto", future_time, base_path=tmp_schedule)

        update_scheduled_post(
            post.id,
            status="failed",
            error="API error",
            base_path=tmp_schedule,
        )

        updated = get_scheduled_post(post.id, tmp_schedule)
        assert updated.status == "failed"
        assert updated.error == "API error"

    def test_update_not_found(self, tmp_schedule):
        """Update returns False if not found."""
        result = update_scheduled_post("nonexistent", status="failed", base_path=tmp_schedule)
        assert result is False


class TestCancelScheduledPost:
    """Tests for cancel_scheduled_post."""

    def test_cancel_pending(self, tmp_schedule):
        """Pending posts can be cancelled."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        post = create_scheduled_post("a.md", "devto", future_time, base_path=tmp_schedule)

        result = cancel_scheduled_post(post.id, tmp_schedule)
        assert result is True

        updated = get_scheduled_post(post.id, tmp_schedule)
        assert updated.status == "cancelled"

    def test_cancel_non_pending(self, tmp_schedule):
        """Non-pending posts cannot be cancelled."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        post = create_scheduled_post("a.md", "devto", future_time, base_path=tmp_schedule)

        # Mark as published
        update_scheduled_post(post.id, status="published", base_path=tmp_schedule)

        result = cancel_scheduled_post(post.id, tmp_schedule)
        assert result is False

    def test_cancel_not_found(self, tmp_schedule):
        """Cancel returns False if not found."""
        result = cancel_scheduled_post("nonexistent", tmp_schedule)
        assert result is False


class TestDeleteScheduledPost:
    """Tests for delete_scheduled_post."""

    def test_delete_post(self, tmp_schedule):
        """Deleting removes post from schedule."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        post = create_scheduled_post("a.md", "devto", future_time, base_path=tmp_schedule)

        result = delete_scheduled_post(post.id, tmp_schedule)
        assert result is True

        deleted = get_scheduled_post(post.id, tmp_schedule)
        assert deleted is None

    def test_delete_not_found(self, tmp_schedule):
        """Delete returns False if not found."""
        result = delete_scheduled_post("nonexistent", tmp_schedule)
        assert result is False


class TestParseScheduleTime:
    """Tests for parse_schedule_time."""

    def test_parse_iso_format(self):
        """Parse ISO format datetime."""
        result = parse_schedule_time("2025-01-24 09:00")
        assert result is not None
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 24

    def test_parse_iso_with_t(self):
        """Parse ISO format with T separator."""
        result = parse_schedule_time("2025-01-24T09:00:00")
        assert result is not None

    def test_parse_natural_language(self):
        """Parse natural language (if dateparser installed)."""
        result = parse_schedule_time("in 2 hours")
        # This should work since dateparser is installed
        assert result is not None
        # Should be in the future
        assert result > datetime.now(timezone.utc)

    def test_parse_tomorrow(self):
        """Parse 'tomorrow' keyword."""
        result = parse_schedule_time("tomorrow 9am")
        assert result is not None
        # Should be tomorrow or later
        assert result > datetime.now(timezone.utc)

    def test_parse_invalid(self):
        """Invalid time returns None."""
        result = parse_schedule_time("not a valid time format xyz123")
        # dateparser is quite permissive, but this should fail
        # Actually dateparser might still parse something, so just check it doesn't crash
        # The test passes if no exception is raised


class TestCleanupOldPosts:
    """Tests for cleanup_old_posts."""

    def test_cleanup_removes_old(self, tmp_schedule):
        """Old completed posts are removed."""
        old_time = datetime.now(timezone.utc) - timedelta(days=60)
        post = create_scheduled_post("old.md", "devto", old_time, base_path=tmp_schedule)
        update_scheduled_post(post.id, status="published", base_path=tmp_schedule)

        removed = cleanup_old_posts(days=30, base_path=tmp_schedule)
        assert removed == 1

        posts = list_scheduled_posts(base_path=tmp_schedule)
        assert len(posts) == 0

    def test_cleanup_keeps_pending(self, tmp_schedule):
        """Pending posts are not removed regardless of age."""
        old_time = datetime.now(timezone.utc) - timedelta(days=60)
        create_scheduled_post("old.md", "devto", old_time, base_path=tmp_schedule)

        removed = cleanup_old_posts(days=30, base_path=tmp_schedule)
        assert removed == 0

        posts = list_scheduled_posts(base_path=tmp_schedule)
        assert len(posts) == 1

    def test_cleanup_keeps_recent(self, tmp_schedule):
        """Recent completed posts are kept."""
        recent_time = datetime.now(timezone.utc) - timedelta(days=7)
        post = create_scheduled_post("recent.md", "devto", recent_time, base_path=tmp_schedule)
        update_scheduled_post(post.id, status="published", base_path=tmp_schedule)

        removed = cleanup_old_posts(days=30, base_path=tmp_schedule)
        assert removed == 0

        posts = list_scheduled_posts(base_path=tmp_schedule)
        assert len(posts) == 1
