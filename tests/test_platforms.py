"""Tests for crier.platforms module."""

import pytest
import requests
from unittest.mock import Mock, patch

from crier.platforms import (
    PLATFORMS,
    get_platform,
    Platform,
    Article,
    PublishResult,
    DevTo,
    Bluesky,
    Mastodon,
    Twitter,
    Threads,
    LinkedIn,
    Telegram,
    Ghost,
    WordPress,
)
from crier.platforms.devto import sanitize_tags


class TestArticleDataclass:
    """Tests for Article dataclass."""

    def test_minimal_article(self):
        article = Article(title="Test", body="Content")
        assert article.title == "Test"
        assert article.body == "Content"
        assert article.description is None
        assert article.tags is None
        assert article.canonical_url is None
        assert article.published is True

    def test_full_article(self, sample_article):
        assert sample_article.title == "Test Article Title"
        assert sample_article.description == "A brief description of the test article"
        assert sample_article.tags == ["python", "testing", "crier"]
        assert sample_article.canonical_url == "https://example.com/test-article"
        assert sample_article.published is True


class TestPublishResultDataclass:
    """Tests for PublishResult dataclass."""

    def test_success_result(self):
        result = PublishResult(
            success=True,
            platform="devto",
            article_id="12345",
            url="https://dev.to/article/12345",
        )
        assert result.success is True
        assert result.platform == "devto"
        assert result.article_id == "12345"
        assert result.url == "https://dev.to/article/12345"
        assert result.error is None
        assert result.requires_confirmation is False

    def test_failure_result(self):
        result = PublishResult(
            success=False,
            platform="bluesky",
            error="Authentication failed",
        )
        assert result.success is False
        assert result.error == "Authentication failed"
        assert result.article_id is None

    def test_manual_mode_result(self):
        result = PublishResult(
            success=True,
            platform="twitter",
            requires_confirmation=True,
            manual_content="Tweet text here",
            compose_url="https://twitter.com/compose/tweet",
        )
        assert result.requires_confirmation is True
        assert result.manual_content == "Tweet text here"
        assert result.compose_url == "https://twitter.com/compose/tweet"


class TestGetPlatform:
    """Tests for get_platform() function."""

    def test_get_known_platform(self):
        platform_cls = get_platform("devto")
        assert platform_cls == DevTo

    def test_get_all_registered_platforms(self):
        for name in PLATFORMS:
            platform_cls = get_platform(name)
            assert issubclass(platform_cls, Platform)

    def test_get_unknown_platform(self):
        with pytest.raises(ValueError) as exc:
            get_platform("nonexistent")
        assert "Unknown platform" in str(exc.value)
        assert "nonexistent" in str(exc.value)


class TestPlatformBase:
    """Tests for Platform base class functionality."""

    def test_default_format_for_manual(self, sample_article):
        """Default format_for_manual returns article body."""
        # DevTo doesn't override format_for_manual, so uses default
        platform = DevTo("test_key")
        result = platform.format_for_manual(sample_article)
        assert result == sample_article.body

    def test_check_content_length_no_limit(self, sample_article):
        """Platforms without max_content_length don't fail length check."""
        platform = DevTo("test_key")
        assert platform.max_content_length is None
        # Should return None (no error)
        error = platform._check_content_length("a" * 10000)
        assert error is None

    def test_check_content_length_within_limit(self):
        """Content within limit passes."""
        platform = Twitter("manual")
        assert platform.max_content_length == 280
        error = platform._check_content_length("Short tweet")
        assert error is None

    def test_check_content_length_exceeds_limit(self):
        """Content exceeding limit returns error."""
        platform = Twitter("manual")
        long_content = "x" * 300
        error = platform._check_content_length(long_content)
        assert error is not None
        assert "too long" in error.lower()
        assert "300" in error
        assert "280" in error


class TestTwitterManualMode:
    """Tests for Twitter manual mode platform."""

    def test_twitter_properties(self):
        platform = Twitter("manual")
        assert platform.name == "twitter"
        assert platform.max_content_length == 280
        assert platform.compose_url == "https://twitter.com/compose/tweet"

    def test_format_for_manual_minimal(self):
        article = Article(title="My Article", body="Full body text")
        platform = Twitter("manual")
        result = platform.format_for_manual(article)
        assert "My Article" in result

    def test_format_for_manual_with_tags(self):
        article = Article(
            title="My Article",
            body="Content",
            tags=["python", "web-dev", "testing"],
        )
        platform = Twitter("manual")
        result = platform.format_for_manual(article)
        assert "#python" in result
        assert "#web_dev" in result  # Hyphens converted to underscores
        assert "#testing" in result

    def test_format_for_manual_with_url(self):
        article = Article(
            title="My Article",
            body="Content",
            canonical_url="https://example.com/article",
        )
        platform = Twitter("manual")
        result = platform.format_for_manual(article)
        assert "https://example.com/article" in result

    def test_format_for_manual_limits_tags(self):
        article = Article(
            title="Test",
            body="Content",
            tags=["one", "two", "three", "four", "five"],
        )
        platform = Twitter("manual")
        result = platform.format_for_manual(article)
        # Only first 3 tags should be included
        assert "#one" in result
        assert "#two" in result
        assert "#three" in result
        assert "#four" not in result

    def test_publish_returns_requires_confirmation(self, sample_article):
        platform = Twitter("manual")
        result = platform.publish(sample_article)
        assert result.success is True
        assert result.requires_confirmation is True
        assert result.manual_content is not None
        assert result.compose_url == "https://twitter.com/compose/tweet"
        assert result.article_id is None  # Not set until user confirms

    def test_publish_too_long_fails(self):
        # Twitter formats: title + hashtags + URL
        # Need total > 280 chars
        article = Article(
            title="A" * 200,
            body="Content",
            canonical_url="https://example.com/very-long-url-path-that-makes-it-exceed",
            tags=["python", "testing", "automation"],
        )
        platform = Twitter("manual")
        result = platform.publish(article)
        assert result.success is False
        assert "too long" in result.error.lower()

    def test_update_not_supported(self, sample_article):
        platform = Twitter("manual")
        result = platform.update("123", sample_article)
        assert result.success is False
        assert "doesn't support editing" in result.error

    def test_list_articles_empty(self):
        platform = Twitter("manual")
        assert platform.list_articles() == []

    def test_get_article_none(self):
        platform = Twitter("manual")
        assert platform.get_article("123") is None

    def test_delete_returns_failure(self):
        """Twitter (manual mode) returns DeleteResult with failure."""
        platform = Twitter("manual")
        result = platform.delete("123")
        assert result.success is False
        assert result.platform == "twitter"
        assert "twitter.com" in result.error.lower()


class TestBluesky:
    """Tests for Bluesky platform."""

    def test_bluesky_properties(self):
        platform = Bluesky("handle.bsky.social:app-password")
        assert platform.name == "bluesky"
        assert platform.max_content_length == 300

    def test_api_key_parsing_with_handle(self):
        platform = Bluesky("handle.bsky.social:app-password-here")
        assert platform.handle == "handle.bsky.social"
        assert platform.app_password == "app-password-here"

    def test_api_key_with_separate_handle(self):
        platform = Bluesky("app-password", handle="myhandle.bsky.social")
        assert platform.handle == "myhandle.bsky.social"
        assert platform.app_password == "app-password"

    @patch("crier.platforms.bluesky.requests.post")
    def test_publish_success(self, mock_post, sample_article):
        # Mock successful authentication
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.return_value = {
            "accessJwt": "token123",
            "did": "did:plc:abc123",
        }

        # Mock successful post creation
        post_response = Mock()
        post_response.status_code = 200
        post_response.json.return_value = {
            "uri": "at://did:plc:abc123/app.bsky.feed.post/xyz789",
        }

        mock_post.side_effect = [auth_response, post_response]

        platform = Bluesky("handle.bsky.social:password")
        result = platform.publish(sample_article)

        assert result.success is True
        assert result.platform == "bluesky"
        assert "xyz789" in result.url

    @patch("crier.platforms.bluesky.requests.post")
    def test_publish_auth_failure(self, mock_post, sample_article):
        mock_response = Mock()
        mock_response.status_code = 401

        mock_post.return_value = mock_response

        platform = Bluesky("handle.bsky.social:wrong-password")
        result = platform.publish(sample_article)

        assert result.success is False
        assert "authenticate" in result.error.lower()

    def test_publish_content_too_long(self):
        # Bluesky composes text from title + description + URL
        # Each separated by \n\n, so we need total > 300 chars
        # title(150) + \n\n(2) + description(120) + \n\n(2) + url(30) = 304
        article = Article(
            title="A" * 150,
            body="Long content",
            description="B" * 120,
            canonical_url="https://example.com/article",
        )
        platform = Bluesky("handle:password")
        result = platform.publish(article)
        assert result.success is False
        assert "too long" in result.error.lower()

    def test_update_not_supported(self, sample_article):
        platform = Bluesky("handle:password")
        result = platform.update("at://did:plc:xxx/app.bsky.feed.post/yyy", sample_article)
        assert result.success is False
        assert "not support editing" in result.error


class TestMastodon:
    """Tests for Mastodon platform."""

    def test_mastodon_properties(self):
        platform = Mastodon("mastodon.social:token123")
        assert platform.name == "mastodon"
        assert platform.max_content_length == 500

    def test_api_key_parsing(self):
        platform = Mastodon("mastodon.social:token123")
        assert platform.instance == "https://mastodon.social"
        assert platform.access_token == "token123"

    def test_api_key_with_separate_instance(self):
        platform = Mastodon("token123", instance="fosstodon.org")
        assert platform.instance == "https://fosstodon.org"
        assert platform.access_token == "token123"

    def test_instance_with_https_prefix(self):
        # When the instance already has https, it's parsed as instance:token
        platform = Mastodon("fosstodon.org:token123")
        assert platform.instance == "https://fosstodon.org"
        assert platform.access_token == "token123"

    @patch("crier.platforms.mastodon.requests.post")
    def test_publish_success(self, mock_post, sample_article):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "123456",
            "url": "https://mastodon.social/@user/123456",
        }
        mock_post.return_value = mock_response

        platform = Mastodon("mastodon.social:token")
        result = platform.publish(sample_article)

        assert result.success is True
        assert result.article_id == "123456"
        assert "mastodon.social" in result.url

    @patch("crier.platforms.mastodon.requests.post")
    def test_publish_failure(self, mock_post, sample_article):
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Invalid token"
        mock_post.return_value = mock_response

        platform = Mastodon("mastodon.social:bad-token")
        result = platform.publish(sample_article)

        assert result.success is False
        assert "401" in result.error


class TestDevTo:
    """Tests for DevTo platform."""

    def test_devto_properties(self):
        platform = DevTo("test_api_key")
        assert platform.name == "devto"
        assert platform.max_content_length is None  # No character limit

    @patch("crier.platforms.devto.requests.post")
    def test_publish_success(self, mock_post, sample_article):
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": 12345,
            "url": "https://dev.to/user/test-article",
        }
        mock_post.return_value = mock_response

        platform = DevTo("test_key")
        result = platform.publish(sample_article)

        assert result.success is True
        assert result.article_id == "12345"
        assert result.url == "https://dev.to/user/test-article"

        # Check that tags are limited to 4
        call_args = mock_post.call_args
        json_data = call_args.kwargs.get("json") or call_args[1].get("json")
        tags = json_data["article"].get("tags", [])
        assert len(tags) <= 4

    @patch("crier.platforms.devto.requests.post")
    def test_publish_failure(self, mock_post, sample_article):
        mock_response = Mock()
        mock_response.status_code = 422
        mock_response.text = "Validation failed"
        mock_post.return_value = mock_response

        platform = DevTo("test_key")
        result = platform.publish(sample_article)

        assert result.success is False
        assert "422" in result.error

    @patch("crier.platforms.devto.requests.get")
    def test_list_articles(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": 1, "title": "Article 1"},
            {"id": 2, "title": "Article 2"},
        ]
        mock_get.return_value = mock_response

        platform = DevTo("test_key")
        articles = platform.list_articles(limit=5)

        assert len(articles) == 2
        assert articles[0]["title"] == "Article 1"

    @patch("crier.platforms.devto.requests.get")
    def test_get_article(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 12345,
            "title": "Test Article",
            "body_markdown": "Content here",
        }
        mock_get.return_value = mock_response

        platform = DevTo("test_key")
        article = platform.get_article("12345")

        assert article is not None
        assert article["title"] == "Test Article"


class TestThreads:
    """Tests for Threads platform."""

    def test_threads_properties(self):
        platform = Threads("user_id:access_token")
        assert platform.name == "threads"
        assert platform.max_content_length == 500

    def test_api_key_parsing(self):
        platform = Threads("123456:token_abc")
        assert platform.user_id == "123456"
        assert platform.access_token == "token_abc"

    def test_invalid_api_key_format(self):
        with pytest.raises(ValueError) as exc:
            Threads("invalid_format")
        assert "user_id:access_token" in str(exc.value)

    def test_update_not_supported(self, sample_article):
        platform = Threads("user:token")
        result = platform.update("123", sample_article)
        assert result.success is False
        assert "not support editing" in result.error

    def test_delete_returns_failure(self):
        """Threads returns DeleteResult with failure (no API support)."""
        platform = Threads("user:token")
        result = platform.delete("123")
        assert result.success is False
        assert result.platform == "threads"
        assert "threads" in result.error.lower()


class TestLinkedIn:
    """Tests for LinkedIn platform."""

    def test_linkedin_properties(self):
        platform = LinkedIn("access_token")
        assert platform.name == "linkedin"
        assert platform.max_content_length == 3000
        assert platform.compose_url == "https://www.linkedin.com/feed/?shareActive=true"

    def test_api_key_parsing_simple(self):
        platform = LinkedIn("access_token")
        assert platform.access_token == "access_token"
        assert platform.person_urn is None

    def test_api_key_parsing_with_urn(self):
        platform = LinkedIn("token123:urn:li:person:abc")
        assert platform.access_token == "token123"
        assert platform.person_urn == "urn:li:person:abc"

    def test_format_for_manual(self):
        article = Article(
            title="My Article",
            body="Full body content",
            description="Brief description",
            tags=["python", "web-dev"],
            canonical_url="https://example.com/article",
        )
        platform = LinkedIn("token")
        result = platform.format_for_manual(article)
        assert "My Article" in result
        assert "Brief description" in result
        assert "#python" in result
        assert "#webdev" in result  # Hyphens removed
        assert "https://example.com/article" in result

    def test_publish_content_too_long(self):
        """Content exceeding 3000 chars should error, not truncate."""
        article = Article(
            title="A" * 2000,
            body="Content",
            description="B" * 1500,
            tags=["python"],
            canonical_url="https://example.com",
        )
        platform = LinkedIn("token:urn:li:person:123")
        # Mock the _get_person_urn to return a valid URN
        platform.person_urn = "urn:li:person:123"
        result = platform.publish(article)
        assert result.success is False
        assert "too long" in result.error.lower()
        assert "3000" in result.error
        assert "--rewrite" in result.error

    @patch("crier.platforms.linkedin.requests.get")
    @patch("crier.platforms.linkedin.requests.post")
    def test_publish_within_limit(self, mock_post, mock_get, sample_article):
        """Content within 3000 chars should succeed."""
        # Mock userinfo response
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"sub": "abc123"})
        )
        # Mock post response
        mock_post.return_value = Mock(
            status_code=201,
            headers={"x-restli-id": "urn:li:share:123456"}
        )

        platform = LinkedIn("token")
        result = platform.publish(sample_article)

        assert result.success is True
        assert result.article_id == "urn:li:share:123456"

    def test_update_not_supported(self, sample_article):
        platform = LinkedIn("token")
        result = platform.update("123", sample_article)
        assert result.success is False
        assert "not support editing" in result.error


class TestPlatformRegistry:
    """Tests for the PLATFORMS registry."""

    def test_all_platforms_registered(self):
        expected = [
            "devto", "bluesky", "mastodon", "hashnode", "medium",
            "linkedin", "ghost", "buttondown", "telegram", "discord",
            "threads", "wordpress", "twitter",
        ]
        for name in expected:
            assert name in PLATFORMS
            assert issubclass(PLATFORMS[name], Platform)

    def test_platform_count(self):
        """Verify we have the expected number of platforms."""
        assert len(PLATFORMS) == 13

    def test_all_platforms_instantiable(self):
        """All platforms can be instantiated with a dummy key."""
        # Some platforms require specific key formats
        special_formats = {
            "threads": "user_id:access_token",
            "ghost": "https://example.com:key_id:key_secret",
            "bluesky": "handle.bsky.social:app_password",
            "mastodon": "mastodon.social:access_token",
            "hashnode": "api_key:publication_id",
            "telegram": "bot_token:chat_id",
            "discord": "https://discord.com/api/webhooks/123/abc",
            "wordpress": "site.wordpress.com:access_token",
        }

        for name, cls in PLATFORMS.items():
            key = special_formats.get(name, "test_key")
            platform = cls(key)
            assert platform.name == name


class TestNetworkFailures:
    """Tests for network failure handling."""

    @patch("crier.platforms.devto.requests.post")
    def test_devto_timeout(self, mock_post, sample_article):
        """DevTo handles timeout gracefully."""
        mock_post.side_effect = requests.Timeout("Connection timed out")

        platform = DevTo("test_key")
        with pytest.raises(requests.Timeout):
            platform.publish(sample_article)

    @patch("crier.platforms.devto.requests.post")
    def test_devto_connection_error(self, mock_post, sample_article):
        """DevTo handles connection error gracefully."""
        mock_post.side_effect = requests.ConnectionError("Failed to connect")

        platform = DevTo("test_key")
        with pytest.raises(requests.ConnectionError):
            platform.publish(sample_article)

    @patch("crier.platforms.bluesky.requests.post")
    def test_bluesky_timeout(self, mock_post, sample_article):
        """Bluesky handles timeout gracefully."""
        mock_post.side_effect = requests.Timeout("Connection timed out")

        platform = Bluesky("handle.bsky.social:password")
        with pytest.raises(requests.Timeout):
            platform.publish(sample_article)

    @patch("crier.platforms.mastodon.requests.post")
    def test_mastodon_timeout(self, mock_post, sample_article):
        """Mastodon handles timeout gracefully."""
        mock_post.side_effect = requests.Timeout("Connection timed out")

        platform = Mastodon("mastodon.social:token")
        with pytest.raises(requests.Timeout):
            platform.publish(sample_article)


class TestInvalidApiKeyFormats:
    """Tests for invalid API key format handling."""

    def test_threads_missing_separator(self):
        """Threads requires user_id:access_token format."""
        with pytest.raises(ValueError) as exc:
            Threads("invalid_format_no_colon")
        assert "user_id:access_token" in str(exc.value)

    def test_telegram_missing_separator(self):
        """Telegram requires bot_token:chat_id format."""
        with pytest.raises(ValueError) as exc:
            Telegram("invalid_format_no_colon")
        assert "bot_token:chat_id" in str(exc.value)

    def test_ghost_invalid_format(self):
        """Ghost requires url:key_id:key_secret format."""
        with pytest.raises(ValueError) as exc:
            Ghost("just_a_key")
        assert "key_id:key_secret" in str(exc.value)

    def test_ghost_two_colons_only(self):
        """Ghost requires exactly url:key_id:key_secret with URL having http(s)://."""
        with pytest.raises(ValueError) as exc:
            Ghost("site.com:key_id")
        assert "key_id:key_secret" in str(exc.value)

    def test_wordpress_com_missing_token(self):
        """WordPress.com requires site:token format."""
        with pytest.raises(ValueError) as exc:
            WordPress("site.wordpress.com")
        assert "access_token" in str(exc.value)

    def test_wordpress_self_hosted_invalid_format(self):
        """Self-hosted WordPress requires url:user:password format."""
        with pytest.raises(ValueError) as exc:
            WordPress("https://site.com")
        assert "username:app_password" in str(exc.value)


class TestDevToTagSanitization:
    """Tests for DevTo tag sanitization."""

    def test_sanitize_tags_basic(self):
        """Basic tag sanitization works."""
        tags = ["Python", "Machine-Learning", "AI"]
        result = sanitize_tags(tags)
        assert result == ["python", "machinelearning", "ai"]

    def test_sanitize_tags_max_four(self):
        """Only first 4 valid tags are kept."""
        tags = ["one", "two", "three", "four", "five", "six"]
        result = sanitize_tags(tags)
        assert len(result) == 4
        assert result == ["one", "two", "three", "four"]

    def test_sanitize_tags_empty_filtered(self):
        """Empty strings after sanitization are filtered out."""
        tags = ["---", "python", "___", "testing"]
        result = sanitize_tags(tags)
        # "---" and "___" become "" and are filtered out
        assert result == ["python", "testing"]

    def test_sanitize_tags_all_special_chars(self):
        """Tags that become empty are filtered."""
        tags = ["---", "___", "###", "valid"]
        result = sanitize_tags(tags)
        assert result == ["valid"]

    def test_sanitize_tags_duplicates_removed(self):
        """Duplicate tags (after sanitization) are removed."""
        tags = ["Python", "python", "PYTHON", "testing"]
        result = sanitize_tags(tags)
        assert result == ["python", "testing"]

    def test_sanitize_tags_preserves_max_after_filtering(self):
        """Max 4 tags after filtering empty/duplicates."""
        tags = ["---", "one", "___", "two", "###", "three", "four", "five"]
        result = sanitize_tags(tags)
        # After filtering: one, two, three, four (first 4 valid)
        assert result == ["one", "two", "three", "four"]


class TestDeleteResult:
    """Tests for DeleteResult dataclass."""

    def test_success_delete_result(self):
        """Create a successful DeleteResult."""
        from crier.platforms.base import DeleteResult

        result = DeleteResult(success=True, platform="devto")
        assert result.success is True
        assert result.platform == "devto"
        assert result.error is None

    def test_failure_delete_result(self):
        """Create a failed DeleteResult."""
        from crier.platforms.base import DeleteResult

        result = DeleteResult(
            success=False,
            platform="bluesky",
            error="Authentication failed",
        )
        assert result.success is False
        assert result.error == "Authentication failed"


class TestPlatformDeleteOperations:
    """Tests for platform delete operations."""

    @patch("crier.platforms.devto.requests.put")
    def test_devto_delete_success(self, mock_put):
        """DevTo delete (unpublish) succeeds."""
        mock_put.return_value = Mock(status_code=200)

        platform = DevTo("test_key")
        result = platform.delete("12345")

        assert result.success is True
        assert result.platform == "devto"
        mock_put.assert_called_once()
        call_json = mock_put.call_args.kwargs.get("json") or mock_put.call_args[1].get("json")
        assert call_json["article"]["published"] is False

    @patch("crier.platforms.devto.requests.put")
    def test_devto_delete_failure(self, mock_put):
        """DevTo delete fails with API error."""
        mock_put.return_value = Mock(status_code=404, text="Not found")

        platform = DevTo("test_key")
        result = platform.delete("12345")

        assert result.success is False
        assert "404" in result.error

    @patch("crier.platforms.bluesky.requests.post")
    def test_bluesky_delete_auth_failure(self, mock_post):
        """Bluesky delete fails when auth fails."""
        mock_post.return_value = Mock(status_code=401)

        platform = Bluesky("handle.bsky.social:password")
        result = platform.delete("at://did:plc:xxx/app.bsky.feed.post/yyy")

        assert result.success is False
        assert "authenticate" in result.error.lower()

    @patch("crier.platforms.bluesky.requests.post")
    def test_bluesky_delete_invalid_format(self, mock_post):
        """Bluesky delete with invalid AT URI format."""
        # Auth succeeds
        auth_response = Mock(status_code=200)
        auth_response.json.return_value = {
            "accessJwt": "token",
            "did": "did:plc:abc",
        }
        mock_post.return_value = auth_response

        platform = Bluesky("handle.bsky.social:password")
        result = platform.delete("invalid-uri")

        assert result.success is False
        assert "Invalid" in result.error

    @patch("crier.platforms.bluesky.requests.post")
    def test_bluesky_delete_success(self, mock_post):
        """Bluesky delete succeeds."""
        auth_response = Mock(status_code=200)
        auth_response.json.return_value = {
            "accessJwt": "token",
            "did": "did:plc:abc",
        }

        delete_response = Mock(status_code=200)

        mock_post.side_effect = [auth_response, delete_response]

        platform = Bluesky("handle.bsky.social:password")
        result = platform.delete("at://did:plc:abc/app.bsky.feed.post/xyz")

        assert result.success is True
        assert result.platform == "bluesky"

    @patch("crier.platforms.bluesky.requests.post")
    def test_bluesky_delete_api_error(self, mock_post):
        """Bluesky delete fails with API error after auth."""
        auth_response = Mock(status_code=200)
        auth_response.json.return_value = {
            "accessJwt": "token",
            "did": "did:plc:abc",
        }

        delete_response = Mock(status_code=500, text="Internal error")

        mock_post.side_effect = [auth_response, delete_response]

        platform = Bluesky("handle.bsky.social:password")
        result = platform.delete("at://did:plc:abc/app.bsky.feed.post/xyz")

        assert result.success is False
        assert "500" in result.error

    @patch("crier.platforms.mastodon.requests.delete")
    def test_mastodon_delete_success(self, mock_delete):
        """Mastodon delete succeeds."""
        mock_delete.return_value = Mock(status_code=200)

        platform = Mastodon("mastodon.social:token")
        result = platform.delete("123456")

        assert result.success is True
        assert result.platform == "mastodon"

    @patch("crier.platforms.mastodon.requests.delete")
    def test_mastodon_delete_failure(self, mock_delete):
        """Mastodon delete fails with API error."""
        mock_delete.return_value = Mock(status_code=403, text="Forbidden")

        platform = Mastodon("mastodon.social:token")
        result = platform.delete("123456")

        assert result.success is False
        assert "403" in result.error


class TestBasePlatformDefaults:
    """Tests for base Platform default methods."""

    def test_default_delete_unsupported(self):
        """Platform with supports_delete=False returns proper result."""
        from crier.platforms.base import Platform, DeleteResult

        # Twitter has supports_delete = False (inherited from manual-mode logic)
        platform = Twitter("manual")
        result = platform.delete("123")
        assert result.success is False
        assert isinstance(result, DeleteResult)

    def test_default_get_stats_returns_none(self):
        """Base Platform.get_stats returns None by default."""
        platform = Twitter("manual")
        assert platform.get_stats("123") is None

    def test_default_publish_thread_unsupported(self):
        """Platform without thread support returns error."""
        from crier.platforms.base import ThreadPublishResult

        platform = DevTo("test_key")
        result = platform.publish_thread(["Post 1", "Post 2"])
        assert result.success is False
        assert "does not support" in result.error

    def test_supports_delete_flag(self):
        """Check supports_delete flags on platforms."""
        assert DevTo.supports_delete is True
        assert Bluesky.supports_delete is True
        assert Mastodon.supports_delete is True

    def test_supports_threads_flag(self):
        """Check supports_threads flags on platforms."""
        assert Bluesky.supports_threads is True
        assert Mastodon.supports_threads is True
        assert DevTo.supports_threads is False
        assert Twitter.supports_threads is False

    def test_thread_max_posts(self):
        """Check thread_max_posts default."""
        assert Bluesky.thread_max_posts == 25
        assert Mastodon.thread_max_posts == 25


class TestBlueskyPublishThread:
    """Tests for Bluesky publish_thread."""

    @patch("crier.platforms.bluesky.requests.post")
    def test_publish_thread_auth_failure(self, mock_post):
        """Thread publish fails when authentication fails."""
        mock_post.return_value = Mock(status_code=401)

        platform = Bluesky("handle.bsky.social:password")
        result = platform.publish_thread(["Post 1", "Post 2"])

        assert result.success is False
        assert "authenticate" in result.error.lower()

    @patch("crier.platforms.bluesky.requests.post")
    def test_publish_thread_success(self, mock_post):
        """Thread publish succeeds with all posts."""
        from crier.platforms.base import ThreadPublishResult

        auth_response = Mock(status_code=200)
        auth_response.json.return_value = {
            "accessJwt": "token",
            "did": "did:plc:abc",
        }

        post1_response = Mock(status_code=200)
        post1_response.json.return_value = {
            "uri": "at://did:plc:abc/app.bsky.feed.post/111",
            "cid": "cid111",
        }

        post2_response = Mock(status_code=200)
        post2_response.json.return_value = {
            "uri": "at://did:plc:abc/app.bsky.feed.post/222",
            "cid": "cid222",
        }

        post3_response = Mock(status_code=200)
        post3_response.json.return_value = {
            "uri": "at://did:plc:abc/app.bsky.feed.post/333",
            "cid": "cid333",
        }

        mock_post.side_effect = [auth_response, post1_response, post2_response, post3_response]

        platform = Bluesky("handle.bsky.social:password")
        result = platform.publish_thread(["Post 1", "Post 2", "Post 3"])

        assert result.success is True
        assert isinstance(result, ThreadPublishResult)
        assert len(result.post_ids) == 3
        assert len(result.post_urls) == 3
        assert result.root_id == "at://did:plc:abc/app.bsky.feed.post/111"
        assert len(result.results) == 3
        for r in result.results:
            assert r.success is True

    @patch("crier.platforms.bluesky.requests.post")
    def test_publish_thread_partial_failure(self, mock_post):
        """Thread publish fails mid-way, returns partial results."""
        auth_response = Mock(status_code=200)
        auth_response.json.return_value = {
            "accessJwt": "token",
            "did": "did:plc:abc",
        }

        post1_response = Mock(status_code=200)
        post1_response.json.return_value = {
            "uri": "at://did:plc:abc/app.bsky.feed.post/111",
            "cid": "cid111",
        }

        post2_response = Mock(status_code=500, text="Server error")

        mock_post.side_effect = [auth_response, post1_response, post2_response]

        platform = Bluesky("handle.bsky.social:password")
        result = platform.publish_thread(["Post 1", "Post 2", "Post 3"])

        assert result.success is False
        assert "Failed on post 2" in result.error
        assert len(result.post_ids) == 1
        assert result.root_id == "at://did:plc:abc/app.bsky.feed.post/111"

    @patch("crier.platforms.bluesky.requests.post")
    def test_publish_thread_content_too_long(self, mock_post):
        """Thread fails if any post exceeds max_content_length."""
        auth_response = Mock(status_code=200)
        auth_response.json.return_value = {
            "accessJwt": "token",
            "did": "did:plc:abc",
        }
        mock_post.return_value = auth_response

        platform = Bluesky("handle.bsky.social:password")
        # Second post exceeds 300 char limit
        result = platform.publish_thread(["Short post", "A" * 400, "Another short"])

        assert result.success is False
        assert "exceeds character limit" in result.error


class TestMastodonPublishThread:
    """Tests for Mastodon publish_thread."""

    @patch("crier.platforms.mastodon.requests.post")
    def test_publish_thread_success(self, mock_post):
        """Thread publish succeeds with all posts."""
        from crier.platforms.base import ThreadPublishResult

        post1_response = Mock(status_code=200)
        post1_response.json.return_value = {
            "id": "111",
            "url": "https://mastodon.social/@user/111",
        }

        post2_response = Mock(status_code=200)
        post2_response.json.return_value = {
            "id": "222",
            "url": "https://mastodon.social/@user/222",
        }

        mock_post.side_effect = [post1_response, post2_response]

        platform = Mastodon("mastodon.social:token")
        result = platform.publish_thread(["Post 1", "Post 2"])

        assert result.success is True
        assert len(result.post_ids) == 2
        assert result.root_id == "111"
        assert result.post_urls[0] == "https://mastodon.social/@user/111"

    @patch("crier.platforms.mastodon.requests.post")
    def test_publish_thread_partial_failure(self, mock_post):
        """Thread publish fails mid-way, returns partial results."""
        post1_response = Mock(status_code=200)
        post1_response.json.return_value = {
            "id": "111",
            "url": "https://mastodon.social/@user/111",
        }

        post2_response = Mock(status_code=422, text="Validation failed")

        mock_post.side_effect = [post1_response, post2_response]

        platform = Mastodon("mastodon.social:token")
        result = platform.publish_thread(["Post 1", "Post 2"])

        assert result.success is False
        assert "Failed on post 2" in result.error
        assert len(result.post_ids) == 1
        assert result.root_id == "111"

    @patch("crier.platforms.mastodon.requests.post")
    def test_publish_thread_content_too_long(self, mock_post):
        """Thread fails if any post exceeds max_content_length."""
        platform = Mastodon("mastodon.social:token")
        # First post exceeds 500 char limit
        result = platform.publish_thread(["A" * 600, "Short post"])

        assert result.success is False
        assert "exceeds character limit" in result.error

    @patch("crier.platforms.mastodon.requests.post")
    def test_publish_thread_sets_reply_to(self, mock_post):
        """Thread posts after the first include in_reply_to_id."""
        post1_response = Mock(status_code=200)
        post1_response.json.return_value = {"id": "111", "url": "url1"}

        post2_response = Mock(status_code=200)
        post2_response.json.return_value = {"id": "222", "url": "url2"}

        mock_post.side_effect = [post1_response, post2_response]

        platform = Mastodon("mastodon.social:token")
        result = platform.publish_thread(["Post 1", "Post 2"])

        assert result.success is True
        # Verify the second post was sent with in_reply_to_id
        second_call = mock_post.call_args_list[1]
        json_data = second_call.kwargs.get("json") or second_call[1].get("json")
        assert json_data["in_reply_to_id"] == "111"


class TestBlueskyThreadReplyReference:
    """Tests for Bluesky thread reply reference structure."""

    @patch("crier.platforms.bluesky.requests.post")
    def test_first_post_has_no_reply(self, mock_post):
        """First post in thread has no reply reference."""
        auth_response = Mock(status_code=200)
        auth_response.json.return_value = {
            "accessJwt": "token",
            "did": "did:plc:abc",
        }

        post_response = Mock(status_code=200)
        post_response.json.return_value = {
            "uri": "at://did:plc:abc/app.bsky.feed.post/111",
            "cid": "cid111",
        }

        mock_post.side_effect = [auth_response, post_response]

        platform = Bluesky("handle.bsky.social:password")
        result = platform.publish_thread(["Single post thread"])

        assert result.success is True

        # Verify the post was sent without reply field
        post_call = mock_post.call_args_list[1]  # Second call is the post (first is auth)
        json_data = post_call.kwargs.get("json") or post_call[1].get("json")
        record = json_data["record"]
        assert "reply" not in record

    @patch("crier.platforms.bluesky.requests.post")
    def test_second_post_has_reply_reference(self, mock_post):
        """Second post includes root and parent reply references."""
        auth_response = Mock(status_code=200)
        auth_response.json.return_value = {
            "accessJwt": "token",
            "did": "did:plc:abc",
        }

        post1_response = Mock(status_code=200)
        post1_response.json.return_value = {
            "uri": "at://did:plc:abc/app.bsky.feed.post/111",
            "cid": "cid111",
        }

        post2_response = Mock(status_code=200)
        post2_response.json.return_value = {
            "uri": "at://did:plc:abc/app.bsky.feed.post/222",
            "cid": "cid222",
        }

        mock_post.side_effect = [auth_response, post1_response, post2_response]

        platform = Bluesky("handle.bsky.social:password")
        result = platform.publish_thread(["Post 1", "Post 2"])

        assert result.success is True

        # Verify second post has reply reference
        post2_call = mock_post.call_args_list[2]
        json_data = post2_call.kwargs.get("json") or post2_call[1].get("json")
        record = json_data["record"]
        assert "reply" in record
        assert record["reply"]["root"]["uri"] == "at://did:plc:abc/app.bsky.feed.post/111"
        assert record["reply"]["root"]["cid"] == "cid111"
        assert record["reply"]["parent"]["uri"] == "at://did:plc:abc/app.bsky.feed.post/111"
        assert record["reply"]["parent"]["cid"] == "cid111"
