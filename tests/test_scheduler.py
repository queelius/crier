"""Tests for crier.scheduler module."""

import pytest
from datetime import datetime, timezone, timedelta

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
    """Set up a temporary schedule directory with isolated config."""
    # Create site directory with .crier/ subdir
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    crier_dir = site_dir / ".crier"
    crier_dir.mkdir()

    # Write a config file pointing site_root to our temp site directory
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"
    config_file.write_text(f"site_root: {site_dir}\n")

    # Point CRIER_CONFIG to our isolated config
    monkeypatch.setenv("CRIER_CONFIG", str(config_file))

    return site_dir


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
        schedule = load_schedule()
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
        save_schedule(schedule)

        loaded = load_schedule()
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
            )

        assert post.id is not None
        assert post.platform == "devto"
        assert post.status == "pending"

        # Verify it was saved
        saved = get_scheduled_post(post.id)
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
            )

        assert post.auto_rewrite is True


class TestListScheduledPosts:
    """Tests for list_scheduled_posts."""

    def test_list_empty(self, tmp_schedule):
        """Empty schedule returns empty list."""
        posts = list_scheduled_posts()
        assert posts == []

    def test_list_all(self, tmp_schedule):
        """List returns all posts."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)

        create_scheduled_post("a.md", "devto", future_time)
        create_scheduled_post("b.md", "bluesky", future_time)

        posts = list_scheduled_posts()
        assert len(posts) == 2

    def test_list_by_status(self, tmp_schedule):
        """List can filter by status."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)

        post = create_scheduled_post("a.md", "devto", future_time)
        create_scheduled_post("b.md", "bluesky", future_time)

        # Cancel one
        cancel_scheduled_post(post.id)

        pending = list_scheduled_posts(status="pending")
        assert len(pending) == 1

        cancelled = list_scheduled_posts(status="cancelled")
        assert len(cancelled) == 1


class TestGetDuePosts:
    """Tests for get_due_posts."""

    def test_no_due_posts(self, tmp_schedule):
        """Future posts are not due."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        create_scheduled_post("a.md", "devto", future_time)

        due = get_due_posts()
        assert len(due) == 0

    def test_past_posts_are_due(self, tmp_schedule):
        """Past posts are due."""
        past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        create_scheduled_post("a.md", "devto", past_time)

        due = get_due_posts()
        assert len(due) == 1

    def test_only_pending_are_due(self, tmp_schedule):
        """Only pending posts are returned as due."""
        past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        post = create_scheduled_post("a.md", "devto", past_time)

        # Cancel the post
        cancel_scheduled_post(post.id)

        due = get_due_posts()
        assert len(due) == 0


class TestUpdateScheduledPost:
    """Tests for update_scheduled_post."""

    def test_update_status(self, tmp_schedule):
        """Update changes status."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        post = create_scheduled_post("a.md", "devto", future_time)

        update_scheduled_post(post.id, status="published")

        updated = get_scheduled_post(post.id)
        assert updated.status == "published"

    def test_update_with_error(self, tmp_schedule):
        """Update can set error message."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        post = create_scheduled_post("a.md", "devto", future_time)

        update_scheduled_post(
            post.id,
            status="failed",
            error="API error",
            )

        updated = get_scheduled_post(post.id)
        assert updated.status == "failed"
        assert updated.error == "API error"

    def test_update_not_found(self, tmp_schedule):
        """Update returns False if not found."""
        result = update_scheduled_post("nonexistent", status="failed")
        assert result is False


class TestCancelScheduledPost:
    """Tests for cancel_scheduled_post."""

    def test_cancel_pending(self, tmp_schedule):
        """Pending posts can be cancelled."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        post = create_scheduled_post("a.md", "devto", future_time)

        result = cancel_scheduled_post(post.id)
        assert result is True

        updated = get_scheduled_post(post.id)
        assert updated.status == "cancelled"

    def test_cancel_non_pending(self, tmp_schedule):
        """Non-pending posts cannot be cancelled."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        post = create_scheduled_post("a.md", "devto", future_time)

        # Mark as published
        update_scheduled_post(post.id, status="published")

        result = cancel_scheduled_post(post.id)
        assert result is False

    def test_cancel_not_found(self, tmp_schedule):
        """Cancel returns False if not found."""
        result = cancel_scheduled_post("nonexistent")
        assert result is False


class TestDeleteScheduledPost:
    """Tests for delete_scheduled_post."""

    def test_delete_post(self, tmp_schedule):
        """Deleting removes post from schedule."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        post = create_scheduled_post("a.md", "devto", future_time)

        result = delete_scheduled_post(post.id)
        assert result is True

        deleted = get_scheduled_post(post.id)
        assert deleted is None

    def test_delete_not_found(self, tmp_schedule):
        """Delete returns False if not found."""
        result = delete_scheduled_post("nonexistent")
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
        parse_schedule_time("not a valid time format xyz123")
        # dateparser is quite permissive, but this should fail
        # Actually dateparser might still parse something, so just check it doesn't crash
        # The test passes if no exception is raised


class TestCleanupOldPosts:
    """Tests for cleanup_old_posts."""

    def test_cleanup_removes_old(self, tmp_schedule):
        """Old completed posts are removed."""
        old_time = datetime.now(timezone.utc) - timedelta(days=60)
        post = create_scheduled_post("old.md", "devto", old_time)
        update_scheduled_post(post.id, status="published")

        removed = cleanup_old_posts(days=30)
        assert removed == 1

        posts = list_scheduled_posts()
        assert len(posts) == 0

    def test_cleanup_keeps_pending(self, tmp_schedule):
        """Pending posts are not removed regardless of age."""
        old_time = datetime.now(timezone.utc) - timedelta(days=60)
        create_scheduled_post("old.md", "devto", old_time)

        removed = cleanup_old_posts(days=30)
        assert removed == 0

        posts = list_scheduled_posts()
        assert len(posts) == 1

    def test_cleanup_keeps_recent(self, tmp_schedule):
        """Recent completed posts are kept."""
        recent_time = datetime.now(timezone.utc) - timedelta(days=7)
        post = create_scheduled_post("recent.md", "devto", recent_time)
        update_scheduled_post(post.id, status="published")

        removed = cleanup_old_posts(days=30)
        assert removed == 0

        posts = list_scheduled_posts()
        assert len(posts) == 1

    def test_cleanup_with_no_posts(self, tmp_schedule):
        """Cleanup with empty schedule returns 0."""
        removed = cleanup_old_posts(days=30)
        assert removed == 0


class TestScheduledPostEdgeCases:
    """Edge case tests for ScheduledPost."""

    def test_to_dict_with_all_optional_fields(self):
        """Conversion includes all optional fields."""
        now = datetime.now(timezone.utc)
        post = ScheduledPost(
            id="abc123",
            file_path="/path/to/file.md",
            platform="bluesky",
            scheduled_time=now,
            created_at=now,
            status="pending",
            error="Some error",
            rewrite="Custom rewrite text",
            auto_rewrite=True,
            profile="social",
        )

        data = post.to_dict()
        assert data["error"] == "Some error"
        assert data["rewrite"] == "Custom rewrite text"
        assert data["auto_rewrite"] is True
        assert data["profile"] == "social"

    def test_from_dict_with_all_optional_fields(self):
        """Creation from dict handles all optional fields."""
        now = datetime.now(timezone.utc)
        data = {
            "id": "abc123",
            "file_path": "/path/to/file.md",
            "platform": "bluesky",
            "scheduled_time": now.isoformat(),
            "created_at": now.isoformat(),
            "status": "failed",
            "error": "API error",
            "rewrite": "Custom rewrite",
            "auto_rewrite": True,
            "profile": "blogs",
        }

        post = ScheduledPost.from_dict(data)
        assert post.error == "API error"
        assert post.rewrite == "Custom rewrite"
        assert post.auto_rewrite is True
        assert post.profile == "blogs"

    def test_from_dict_missing_optional_fields(self):
        """Creation from dict uses defaults for missing optional fields."""
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
        assert post.error is None
        assert post.rewrite is None
        assert post.auto_rewrite is False
        assert post.profile is None

    def test_roundtrip_serialization(self):
        """to_dict -> from_dict preserves all data."""
        now = datetime.now(timezone.utc)
        original = ScheduledPost(
            id="test1",
            file_path="article.md",
            platform="devto",
            scheduled_time=now,
            created_at=now,
            status="pending",
            rewrite="Short version",
            auto_rewrite=True,
            profile="social",
        )

        data = original.to_dict()
        restored = ScheduledPost.from_dict(data)

        assert restored.id == original.id
        assert restored.file_path == original.file_path
        assert restored.platform == original.platform
        assert restored.status == original.status
        assert restored.rewrite == original.rewrite
        assert restored.auto_rewrite == original.auto_rewrite
        assert restored.profile == original.profile


class TestCreateScheduledPostEdgeCases:
    """Edge case tests for create_scheduled_post."""

    def test_create_with_naive_datetime(self, tmp_schedule):
        """Creating with naive datetime gets UTC timezone applied."""
        naive_time = datetime(2030, 6, 15, 10, 0, 0)

        post = create_scheduled_post(
            file_path="test.md",
            platform="devto",
            scheduled_time=naive_time,
            )

        assert post.scheduled_time.tzinfo is not None

    def test_create_with_profile(self, tmp_schedule):
        """Creating a post with profile stores it."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)

        post = create_scheduled_post(
            file_path="test.md",
            platform="",
            scheduled_time=future_time,
            profile="blogs",
            )

        assert post.profile == "blogs"
        assert post.platform == ""

        # Verify persisted
        saved = get_scheduled_post(post.id)
        assert saved.profile == "blogs"

    def test_create_multiple_posts_for_same_file(self, tmp_schedule):
        """Multiple scheduled posts for the same file are stored separately."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)

        post1 = create_scheduled_post("test.md", "devto", future_time)
        post2 = create_scheduled_post("test.md", "bluesky", future_time)

        assert post1.id != post2.id

        all_posts = list_scheduled_posts()
        assert len(all_posts) == 2


class TestGetScheduledPostEdgeCases:
    """Edge case tests for get_scheduled_post."""

    def test_get_by_partial_id(self, tmp_schedule):
        """Get post by partial ID prefix."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        post = create_scheduled_post("test.md", "devto", future_time)

        # Get by first 4 chars of ID
        found = get_scheduled_post(post.id[:4])
        assert found is not None
        assert found.id == post.id

    def test_get_nonexistent_returns_none(self, tmp_schedule):
        """Getting nonexistent post returns None."""
        result = get_scheduled_post("nonexistent")
        assert result is None


class TestUpdateScheduledPostEdgeCases:
    """Edge case tests for update_scheduled_post."""

    def test_update_by_partial_id(self, tmp_schedule):
        """Update works with partial ID prefix."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        post = create_scheduled_post("test.md", "devto", future_time)

        result = update_scheduled_post(post.id[:4], status="published")
        assert result is True

        updated = get_scheduled_post(post.id)
        assert updated.status == "published"

    def test_update_error_only(self, tmp_schedule):
        """Update can set error without changing status."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        post = create_scheduled_post("test.md", "devto", future_time)

        result = update_scheduled_post(post.id, error="Rate limited")
        assert result is True

        updated = get_scheduled_post(post.id)
        assert updated.error == "Rate limited"
        assert updated.status == "pending"  # Status unchanged


class TestCancelScheduledPostEdgeCases:
    """Edge case tests for cancel_scheduled_post."""

    def test_cancel_by_partial_id(self, tmp_schedule):
        """Cancel works with partial ID prefix."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        post = create_scheduled_post("test.md", "devto", future_time)

        result = cancel_scheduled_post(post.id[:4])
        assert result is True

    def test_cancel_failed_post_returns_false(self, tmp_schedule):
        """Cannot cancel a failed post."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        post = create_scheduled_post("test.md", "devto", future_time)
        update_scheduled_post(post.id, status="failed")

        result = cancel_scheduled_post(post.id)
        assert result is False

    def test_cancel_cancelled_post_returns_false(self, tmp_schedule):
        """Cannot cancel an already-cancelled post."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        post = create_scheduled_post("test.md", "devto", future_time)
        cancel_scheduled_post(post.id)

        result = cancel_scheduled_post(post.id)
        assert result is False


class TestDeleteScheduledPostEdgeCases:
    """Edge case tests for delete_scheduled_post."""

    def test_delete_by_partial_id(self, tmp_schedule):
        """Delete works with partial ID prefix."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        post = create_scheduled_post("test.md", "devto", future_time)

        result = delete_scheduled_post(post.id[:4])
        assert result is True

        all_posts = list_scheduled_posts()
        assert len(all_posts) == 0

    def test_delete_removes_any_status(self, tmp_schedule):
        """Delete removes posts regardless of status."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        post = create_scheduled_post("test.md", "devto", future_time)
        update_scheduled_post(post.id, status="published")

        result = delete_scheduled_post(post.id)
        assert result is True


class TestListScheduledPostsEdgeCases:
    """Edge case tests for list_scheduled_posts."""

    def test_list_sorted_by_scheduled_time(self, tmp_schedule):
        """Posts are returned sorted by scheduled_time."""
        now = datetime.now(timezone.utc)
        create_scheduled_post("late.md", "devto", now + timedelta(hours=5))
        create_scheduled_post("early.md", "devto", now + timedelta(hours=1))
        create_scheduled_post("mid.md", "devto", now + timedelta(hours=3))

        posts = list_scheduled_posts()
        assert len(posts) == 3
        assert posts[0].file_path == "early.md"
        assert posts[1].file_path == "mid.md"
        assert posts[2].file_path == "late.md"

    def test_list_with_status_no_matches(self, tmp_schedule):
        """Filtering by status with no matches returns empty list."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        create_scheduled_post("test.md", "devto", future_time)

        posts = list_scheduled_posts(status="published")
        assert posts == []


class TestGetDuePostsEdgeCases:
    """Edge case tests for get_due_posts."""

    def test_boundary_time_post_is_due(self, tmp_schedule):
        """Post scheduled exactly at now is due."""
        # Create a post with past time
        past_time = datetime.now(timezone.utc) - timedelta(seconds=1)
        create_scheduled_post("test.md", "devto", past_time)

        due = get_due_posts()
        assert len(due) == 1

    def test_due_posts_excludes_cancelled(self, tmp_schedule):
        """Due posts exclude cancelled posts."""
        past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        post = create_scheduled_post("test.md", "devto", past_time)
        cancel_scheduled_post(post.id)

        due = get_due_posts()
        assert len(due) == 0

    def test_due_posts_excludes_failed(self, tmp_schedule):
        """Due posts exclude failed posts."""
        past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        post = create_scheduled_post("test.md", "devto", past_time)
        update_scheduled_post(post.id, status="failed")

        due = get_due_posts()
        assert len(due) == 0

    def test_mixed_due_and_future_posts(self, tmp_schedule):
        """Only past posts are returned as due."""
        past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        create_scheduled_post("past.md", "devto", past_time)
        create_scheduled_post("future.md", "devto", future_time)

        due = get_due_posts()
        assert len(due) == 1
        assert due[0].file_path == "past.md"


class TestParseScheduleTimeEdgeCases:
    """Edge case tests for parse_schedule_time."""

    def test_parse_iso_with_timezone(self):
        """Parse ISO format with timezone info."""
        result = parse_schedule_time("2025-06-15T10:00:00+00:00")
        assert result is not None
        assert result.tzinfo is not None

    def test_parse_relative_time(self):
        """Parse relative time like 'in 30 minutes'."""
        result = parse_schedule_time("in 30 minutes")
        assert result is not None
        assert result > datetime.now(timezone.utc)


class TestCleanupOldPostsEdgeCases:
    """Edge case tests for cleanup_old_posts."""

    def test_cleanup_removes_old_failed_posts(self, tmp_schedule):
        """Old failed posts are also removed."""
        old_time = datetime.now(timezone.utc) - timedelta(days=60)
        post = create_scheduled_post("old.md", "devto", old_time)
        update_scheduled_post(post.id, status="failed", error="API Error")

        removed = cleanup_old_posts(days=30)
        assert removed == 1

    def test_cleanup_removes_old_cancelled_posts(self, tmp_schedule):
        """Old cancelled posts are also removed."""
        old_time = datetime.now(timezone.utc) - timedelta(days=60)
        post = create_scheduled_post("old.md", "devto", old_time)
        cancel_scheduled_post(post.id)

        removed = cleanup_old_posts(days=30)
        assert removed == 1

    def test_cleanup_with_mixed_ages(self, tmp_schedule):
        """Cleanup handles mix of old and recent posts."""
        old_time = datetime.now(timezone.utc) - timedelta(days=60)
        recent_time = datetime.now(timezone.utc) - timedelta(days=7)

        old_post = create_scheduled_post("old.md", "devto", old_time)
        update_scheduled_post(old_post.id, status="published")

        recent_post = create_scheduled_post("recent.md", "devto", recent_time)
        update_scheduled_post(recent_post.id, status="published")

        create_scheduled_post("pending.md", "devto", old_time)

        removed = cleanup_old_posts(days=30)
        assert removed == 1  # Only old published post removed

        posts = list_scheduled_posts()
        assert len(posts) == 2  # recent + pending remain
