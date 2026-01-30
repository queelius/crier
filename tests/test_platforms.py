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
    Hashnode,
    Medium,
    Buttondown,
    Discord,
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


class TestGhost:
    """Tests for Ghost platform."""

    def _make_ghost(self) -> Ghost:
        """Create a Ghost instance with a valid hex secret."""
        # Ghost requires hex-decodable secret for JWT signing
        return Ghost("https://myblog.com:key_id_123:aabbccdd00112233aabbccdd00112233")

    def test_ghost_properties(self):
        ghost = self._make_ghost()
        assert ghost.name == "ghost"
        assert ghost.base_url == "https://myblog.com"
        assert ghost.key_id == "key_id_123"
        assert ghost.key_secret == "aabbccdd00112233aabbccdd00112233"

    def test_ghost_invalid_format_no_colons(self):
        with pytest.raises(ValueError) as exc:
            Ghost("just_a_key")
        assert "key_id:key_secret" in str(exc.value)

    def test_ghost_invalid_format_one_colon(self):
        with pytest.raises(ValueError) as exc:
            Ghost("site.com:key_id")
        assert "key_id:key_secret" in str(exc.value)

    def test_ghost_strips_trailing_slash(self):
        ghost = Ghost("https://myblog.com/:key_id:aabbccdd00112233aabbccdd00112233")
        assert ghost.base_url == "https://myblog.com"

    def test_make_token_returns_jwt_string(self):
        ghost = self._make_ghost()
        token = ghost._make_token()
        # JWT has three dot-separated parts
        parts = token.split(".")
        assert len(parts) == 3

    def test_get_headers_includes_ghost_auth(self):
        ghost = self._make_ghost()
        headers = ghost._get_headers()
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Ghost ")
        assert headers["Content-Type"] == "application/json"

    @patch("crier.platforms.ghost.requests.post")
    def test_publish_success(self, mock_post, sample_article):
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "posts": [{
                "id": "ghost_post_1",
                "url": "https://myblog.com/test-article/",
            }]
        }
        mock_post.return_value = mock_response

        ghost = self._make_ghost()
        result = ghost.publish(sample_article)

        assert result.success is True
        assert result.platform == "ghost"
        assert result.article_id == "ghost_post_1"
        assert result.url == "https://myblog.com/test-article/"

        # Verify request payload
        call_kwargs = mock_post.call_args
        json_data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        post_data = json_data["posts"][0]
        assert post_data["title"] == sample_article.title
        assert post_data["html"] == sample_article.body
        assert post_data["status"] == "published"
        assert post_data["custom_excerpt"] == sample_article.description
        assert post_data["canonical_url"] == sample_article.canonical_url
        assert len(post_data["tags"]) == 3
        assert post_data["tags"][0] == {"name": "python"}

    @patch("crier.platforms.ghost.requests.post")
    def test_publish_draft(self, mock_post):
        article = Article(title="Draft Post", body="Content", published=False)
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "posts": [{"id": "d1", "url": "https://myblog.com/draft/"}]
        }
        mock_post.return_value = mock_response

        ghost = self._make_ghost()
        result = ghost.publish(article)

        assert result.success is True
        call_kwargs = mock_post.call_args
        json_data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert json_data["posts"][0]["status"] == "draft"

    @patch("crier.platforms.ghost.requests.post")
    def test_publish_minimal_article(self, mock_post):
        article = Article(title="Simple", body="Hello")
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "posts": [{"id": "s1", "url": "https://myblog.com/simple/"}]
        }
        mock_post.return_value = mock_response

        ghost = self._make_ghost()
        result = ghost.publish(article)

        assert result.success is True
        call_kwargs = mock_post.call_args
        json_data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        post_data = json_data["posts"][0]
        assert "custom_excerpt" not in post_data
        assert "tags" not in post_data
        assert "canonical_url" not in post_data

    @patch("crier.platforms.ghost.requests.post")
    def test_publish_failure(self, mock_post, sample_article):
        mock_response = Mock()
        mock_response.status_code = 422
        mock_response.text = "Validation failed: title is required"
        mock_post.return_value = mock_response

        ghost = self._make_ghost()
        result = ghost.publish(sample_article)

        assert result.success is False
        assert "422" in result.error
        assert "Validation failed" in result.error

    @patch("crier.platforms.ghost.requests.get")
    @patch("crier.platforms.ghost.requests.put")
    def test_update_success(self, mock_put, mock_get, sample_article):
        # Mock get_article (fetches current post for updated_at)
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "posts": [{"id": "g1", "updated_at": "2025-01-01T00:00:00Z"}]
            }),
        )
        # Mock update response
        mock_put.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "posts": [{"id": "g1", "url": "https://myblog.com/updated/"}]
            }),
        )

        ghost = self._make_ghost()
        result = ghost.update("g1", sample_article)

        assert result.success is True
        assert result.article_id == "g1"
        assert result.url == "https://myblog.com/updated/"

    @patch("crier.platforms.ghost.requests.get")
    def test_update_article_not_found(self, mock_get, sample_article):
        mock_get.return_value = Mock(status_code=404, json=Mock(return_value={}))

        ghost = self._make_ghost()
        result = ghost.update("nonexistent", sample_article)

        assert result.success is False
        assert "not found" in result.error

    @patch("crier.platforms.ghost.requests.get")
    @patch("crier.platforms.ghost.requests.put")
    def test_update_api_error(self, mock_put, mock_get, sample_article):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "posts": [{"id": "g1", "updated_at": "2025-01-01T00:00:00Z"}]
            }),
        )
        mock_put.return_value = Mock(status_code=500, text="Internal Server Error")

        ghost = self._make_ghost()
        result = ghost.update("g1", sample_article)

        assert result.success is False
        assert "500" in result.error

    @patch("crier.platforms.ghost.requests.get")
    def test_list_articles_success(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "posts": [
                    {"id": "p1", "title": "First Post", "status": "published", "url": "https://myblog.com/first/"},
                    {"id": "p2", "title": "Draft Post", "status": "draft", "url": "https://myblog.com/draft/"},
                ]
            }),
        )

        ghost = self._make_ghost()
        articles = ghost.list_articles(limit=5)

        assert len(articles) == 2
        assert articles[0]["id"] == "p1"
        assert articles[0]["title"] == "First Post"
        assert articles[0]["published"] is True
        assert articles[1]["published"] is False

    @patch("crier.platforms.ghost.requests.get")
    def test_list_articles_api_error(self, mock_get):
        mock_get.return_value = Mock(status_code=401, text="Unauthorized")

        ghost = self._make_ghost()
        articles = ghost.list_articles()

        assert articles == []

    @patch("crier.platforms.ghost.requests.get")
    def test_get_article_success(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "posts": [{"id": "g1", "title": "My Post", "html": "<p>Content</p>"}]
            }),
        )

        ghost = self._make_ghost()
        article = ghost.get_article("g1")

        assert article is not None
        assert article["id"] == "g1"
        assert article["title"] == "My Post"

    @patch("crier.platforms.ghost.requests.get")
    def test_get_article_not_found(self, mock_get):
        mock_get.return_value = Mock(status_code=404)

        ghost = self._make_ghost()
        article = ghost.get_article("nonexistent")

        assert article is None

    @patch("crier.platforms.ghost.requests.get")
    def test_get_article_empty_posts(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"posts": []}),
        )

        ghost = self._make_ghost()
        article = ghost.get_article("g1")

        assert article is None

    @patch("crier.platforms.ghost.requests.delete")
    def test_delete_success(self, mock_delete):
        mock_delete.return_value = Mock(status_code=204)

        ghost = self._make_ghost()
        result = ghost.delete("g1")

        assert result.success is True
        assert result.platform == "ghost"

    @patch("crier.platforms.ghost.requests.delete")
    def test_delete_failure(self, mock_delete):
        mock_delete.return_value = Mock(status_code=404, text="Not found")

        ghost = self._make_ghost()
        result = ghost.delete("nonexistent")

        assert result.success is False
        assert "404" in result.error


class TestWordPress:
    """Tests for WordPress platform."""

    def test_wpcom_properties(self):
        wp = WordPress("site.wordpress.com:access_token")
        assert wp.name == "wordpress"
        assert wp.is_wpcom is True
        assert wp.site == "site.wordpress.com"
        assert wp.access_token == "access_token"
        assert "Bearer" in wp.headers["Authorization"]
        assert "public-api.wordpress.com" in wp.base_url

    def test_self_hosted_properties(self):
        wp = WordPress("https://myblog.com:admin:app_pass_123")
        assert wp.name == "wordpress"
        assert wp.is_wpcom is False
        assert wp.username == "admin"
        assert wp.password == "app_pass_123"
        assert "Basic" in wp.headers["Authorization"]
        assert wp.base_url == "https://myblog.com/wp-json/wp/v2"

    def test_wpcom_missing_token(self):
        with pytest.raises(ValueError) as exc:
            WordPress("site.wordpress.com")
        assert "access_token" in str(exc.value)

    def test_self_hosted_missing_password(self):
        with pytest.raises(ValueError) as exc:
            WordPress("https://site.com")
        assert "username:app_password" in str(exc.value)

    def test_self_hosted_username_only_no_password(self):
        """Self-hosted with URL and username but no app_password should fail."""
        with pytest.raises(ValueError) as exc:
            WordPress("https://site.com:usernameonly")
        assert "username:app_password" in str(exc.value)

    @patch("crier.platforms.wordpress.requests.post")
    def test_publish_success_wpcom(self, mock_post, sample_article):
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": 42,
            "link": "https://site.wordpress.com/2025/01/test-article/",
        }
        mock_post.return_value = mock_response

        wp = WordPress("site.wordpress.com:token123")
        result = wp.publish(sample_article)

        assert result.success is True
        assert result.article_id == "42"
        assert result.url == "https://site.wordpress.com/2025/01/test-article/"
        assert result.platform == "wordpress"

    @patch("crier.platforms.wordpress.requests.post")
    def test_publish_success_200(self, mock_post, sample_article):
        """WordPress can return 200 or 201 on publish success."""
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"id": 1, "link": "https://wp.com/post/"}),
        )

        wp = WordPress("site.wordpress.com:token")
        result = wp.publish(sample_article)

        assert result.success is True

    @patch("crier.platforms.wordpress.requests.post")
    def test_publish_sends_correct_payload(self, mock_post, sample_article):
        mock_post.return_value = Mock(
            status_code=201,
            json=Mock(return_value={"id": 1, "link": "https://wp.com/p/"}),
        )

        wp = WordPress("site.wordpress.com:token")
        wp.publish(sample_article)

        call_kwargs = mock_post.call_args
        json_data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert json_data["title"] == sample_article.title
        assert json_data["content"] == sample_article.body
        assert json_data["status"] == "publish"
        assert json_data["excerpt"] == sample_article.description
        assert json_data["tags"] == sample_article.tags

    @patch("crier.platforms.wordpress.requests.post")
    def test_publish_draft(self, mock_post):
        article = Article(title="Draft", body="Content", published=False)
        mock_post.return_value = Mock(
            status_code=201,
            json=Mock(return_value={"id": 2, "link": "https://wp.com/draft/"}),
        )

        wp = WordPress("site.wordpress.com:token")
        wp.publish(article)

        call_kwargs = mock_post.call_args
        json_data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert json_data["status"] == "draft"

    @patch("crier.platforms.wordpress.requests.post")
    def test_publish_minimal_article(self, mock_post):
        article = Article(title="Simple", body="Hello")
        mock_post.return_value = Mock(
            status_code=201,
            json=Mock(return_value={"id": 3, "link": "https://wp.com/simple/"}),
        )

        wp = WordPress("site.wordpress.com:token")
        wp.publish(article)

        call_kwargs = mock_post.call_args
        json_data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "excerpt" not in json_data
        assert "tags" not in json_data

    @patch("crier.platforms.wordpress.requests.post")
    def test_publish_failure(self, mock_post, sample_article):
        mock_post.return_value = Mock(status_code=403, text="Forbidden")

        wp = WordPress("site.wordpress.com:token")
        result = wp.publish(sample_article)

        assert result.success is False
        assert "403" in result.error

    @patch("crier.platforms.wordpress.requests.post")
    def test_update_success(self, mock_post, sample_article):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"id": 42, "link": "https://wp.com/updated/"}),
        )

        wp = WordPress("site.wordpress.com:token")
        result = wp.update("42", sample_article)

        assert result.success is True
        assert result.article_id == "42"
        assert result.url == "https://wp.com/updated/"

    @patch("crier.platforms.wordpress.requests.post")
    def test_update_failure(self, mock_post, sample_article):
        mock_post.return_value = Mock(status_code=404, text="Not found")

        wp = WordPress("site.wordpress.com:token")
        result = wp.update("999", sample_article)

        assert result.success is False
        assert "404" in result.error

    @patch("crier.platforms.wordpress.requests.get")
    def test_list_articles_success(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value=[
                {"id": 1, "title": {"rendered": "Post One"}, "status": "publish", "link": "https://wp.com/one/"},
                {"id": 2, "title": {"rendered": "Post Two"}, "status": "draft", "link": "https://wp.com/two/"},
            ]),
        )

        wp = WordPress("site.wordpress.com:token")
        articles = wp.list_articles(limit=5)

        assert len(articles) == 2
        assert articles[0]["id"] == 1
        assert articles[0]["title"] == "Post One"
        assert articles[0]["published"] is True
        assert articles[1]["published"] is False

    @patch("crier.platforms.wordpress.requests.get")
    def test_list_articles_api_error(self, mock_get):
        mock_get.return_value = Mock(status_code=401, text="Unauthorized")

        wp = WordPress("site.wordpress.com:token")
        articles = wp.list_articles()

        assert articles == []

    @patch("crier.platforms.wordpress.requests.get")
    def test_get_article_success(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"id": 42, "title": {"rendered": "My Post"}}),
        )

        wp = WordPress("site.wordpress.com:token")
        article = wp.get_article("42")

        assert article is not None
        assert article["id"] == 42

    @patch("crier.platforms.wordpress.requests.get")
    def test_get_article_not_found(self, mock_get):
        mock_get.return_value = Mock(status_code=404)

        wp = WordPress("site.wordpress.com:token")
        article = wp.get_article("999")

        assert article is None

    @patch("crier.platforms.wordpress.requests.delete")
    def test_delete_success(self, mock_delete):
        mock_delete.return_value = Mock(status_code=200)

        wp = WordPress("site.wordpress.com:token")
        result = wp.delete("42")

        assert result.success is True
        assert result.platform == "wordpress"

    @patch("crier.platforms.wordpress.requests.delete")
    def test_delete_failure(self, mock_delete):
        mock_delete.return_value = Mock(status_code=403, text="Forbidden")

        wp = WordPress("site.wordpress.com:token")
        result = wp.delete("42")

        assert result.success is False
        assert "403" in result.error


class TestHashnode:
    """Tests for Hashnode platform."""

    def test_hashnode_properties(self):
        hn = Hashnode("mytoken:pub123")
        assert hn.name == "hashnode"
        assert hn.token == "mytoken"
        assert hn.publication_id == "pub123"

    def test_hashnode_token_only(self):
        hn = Hashnode("mytoken")
        assert hn.token == "mytoken"
        assert hn.publication_id is None

    def test_hashnode_with_explicit_publication_id(self):
        hn = Hashnode("mytoken", publication_id="explicit_pub")
        assert hn.token == "mytoken"
        assert hn.publication_id == "explicit_pub"

    @patch("crier.platforms.hashnode.requests.post")
    def test_graphql_success(self, mock_post):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"data": {"me": {"id": "user1"}}}),
        )

        hn = Hashnode("token:pub1")
        result = hn._graphql("query { me { id } }")

        assert result["data"]["me"]["id"] == "user1"

    @patch("crier.platforms.hashnode.requests.post")
    def test_graphql_failure(self, mock_post):
        mock_post.return_value = Mock(status_code=401, text="Unauthorized")

        hn = Hashnode("bad_token:pub1")
        result = hn._graphql("query { me { id } }")

        assert "errors" in result
        assert "401" in result["errors"][0]["message"]

    @patch("crier.platforms.hashnode.requests.post")
    def test_get_publication_id_cached(self, mock_post):
        """When publication_id is already set, no API call is made."""
        hn = Hashnode("token:pub123")
        result = hn._get_publication_id()

        assert result == "pub123"
        mock_post.assert_not_called()

    @patch("crier.platforms.hashnode.requests.post")
    def test_get_publication_id_from_api(self, mock_post):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "data": {
                    "me": {
                        "publications": {
                            "edges": [{"node": {"id": "fetched_pub_id"}}]
                        }
                    }
                }
            }),
        )

        hn = Hashnode("token")
        result = hn._get_publication_id()

        assert result == "fetched_pub_id"

    @patch("crier.platforms.hashnode.requests.post")
    def test_get_publication_id_no_publications(self, mock_post):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "data": {"me": {"publications": {"edges": []}}}
            }),
        )

        hn = Hashnode("token")
        result = hn._get_publication_id()

        assert result is None

    @patch("crier.platforms.hashnode.requests.post")
    def test_publish_success(self, mock_post, sample_article):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "data": {
                    "publishPost": {
                        "post": {
                            "id": "hn_post_1",
                            "url": "https://blog.hashnode.dev/test-article",
                            "slug": "test-article",
                        }
                    }
                }
            }),
        )

        hn = Hashnode("token:pub123")
        result = hn.publish(sample_article)

        assert result.success is True
        assert result.article_id == "hn_post_1"
        assert result.url == "https://blog.hashnode.dev/test-article"

    @patch("crier.platforms.hashnode.requests.post")
    def test_publish_sends_correct_variables(self, mock_post, sample_article):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "data": {"publishPost": {"post": {"id": "1", "url": "https://x.com/1"}}}
            }),
        )

        hn = Hashnode("token:pub123")
        hn.publish(sample_article)

        call_kwargs = mock_post.call_args
        json_data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        variables = json_data["variables"]
        input_data = variables["input"]

        assert input_data["publicationId"] == "pub123"
        assert input_data["title"] == sample_article.title
        assert input_data["contentMarkdown"] == sample_article.body
        assert input_data["originalArticleURL"] == sample_article.canonical_url
        assert len(input_data["tags"]) == 3
        assert input_data["subtitle"] == sample_article.description[:150]

    @patch("crier.platforms.hashnode.requests.post")
    def test_publish_no_publication(self, mock_post, sample_article):
        """Publish fails when no publication is found."""
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "data": {"me": {"publications": {"edges": []}}}
            }),
        )

        hn = Hashnode("token")
        result = hn.publish(sample_article)

        assert result.success is False
        assert "No publication found" in result.error

    @patch("crier.platforms.hashnode.requests.post")
    def test_publish_graphql_error(self, mock_post, sample_article):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "errors": [{"message": "Invalid slug format"}]
            }),
        )

        hn = Hashnode("token:pub123")
        result = hn.publish(sample_article)

        assert result.success is False
        assert "Invalid slug format" in result.error

    @patch("crier.platforms.hashnode.requests.post")
    def test_update_success(self, mock_post, sample_article):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "data": {
                    "updatePost": {
                        "post": {
                            "id": "hn_post_1",
                            "url": "https://blog.hashnode.dev/updated",
                        }
                    }
                }
            }),
        )

        hn = Hashnode("token:pub123")
        result = hn.update("hn_post_1", sample_article)

        assert result.success is True
        assert result.article_id == "hn_post_1"

    @patch("crier.platforms.hashnode.requests.post")
    def test_update_graphql_error(self, mock_post, sample_article):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "errors": [{"message": "Post not found"}]
            }),
        )

        hn = Hashnode("token:pub123")
        result = hn.update("bad_id", sample_article)

        assert result.success is False
        assert "Post not found" in result.error

    @patch("crier.platforms.hashnode.requests.post")
    def test_list_articles_success(self, mock_post):
        # First call: publish id is already set, so it goes straight to posts query
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "data": {
                    "publication": {
                        "posts": {
                            "edges": [
                                {"node": {"id": "p1", "title": "Long Title That Gets Truncated To Fifty Characters For Display", "url": "https://hn.dev/p1", "publishedAt": "2025-01-01"}},
                                {"node": {"id": "p2", "title": "Short", "url": "https://hn.dev/p2", "publishedAt": "2025-01-02"}},
                            ]
                        }
                    }
                }
            }),
        )

        hn = Hashnode("token:pub123")
        articles = hn.list_articles(limit=5)

        assert len(articles) == 2
        assert articles[0]["id"] == "p1"
        assert len(articles[0]["title"]) <= 50
        assert articles[0]["published"] is True
        assert articles[1]["title"] == "Short"

    @patch("crier.platforms.hashnode.requests.post")
    def test_list_articles_no_publication(self, mock_post):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "data": {"me": {"publications": {"edges": []}}}
            }),
        )

        hn = Hashnode("token")
        articles = hn.list_articles()

        assert articles == []

    @patch("crier.platforms.hashnode.requests.post")
    def test_get_article_success(self, mock_post):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "data": {
                    "post": {
                        "id": "p1",
                        "title": "My Post",
                        "content": {"markdown": "Hello world"},
                        "url": "https://hn.dev/p1",
                    }
                }
            }),
        )

        hn = Hashnode("token:pub123")
        article = hn.get_article("p1")

        assert article is not None
        assert article["id"] == "p1"
        assert article["title"] == "My Post"

    @patch("crier.platforms.hashnode.requests.post")
    def test_get_article_not_found(self, mock_post):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"data": {"post": None}}),
        )

        hn = Hashnode("token:pub123")
        article = hn.get_article("nonexistent")

        assert article is None

    @patch("crier.platforms.hashnode.requests.post")
    def test_delete_success(self, mock_post):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "data": {"removePost": {"post": {"id": "p1"}}}
            }),
        )

        hn = Hashnode("token:pub123")
        result = hn.delete("p1")

        assert result.success is True
        assert result.platform == "hashnode"

    @patch("crier.platforms.hashnode.requests.post")
    def test_delete_error(self, mock_post):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "errors": [{"message": "Not authorized to delete this post"}]
            }),
        )

        hn = Hashnode("token:pub123")
        result = hn.delete("p1")

        assert result.success is False
        assert "Not authorized" in result.error


class TestMedium:
    """Tests for Medium platform."""

    def test_medium_properties(self):
        m = Medium("integration_token")
        assert m.name == "medium"
        assert m.supports_delete is False
        assert m.compose_url == "https://medium.com/new-story"

    def test_format_for_manual_full(self):
        article = Article(
            title="My Article",
            body="Full body content here.",
            description="A brief description",
            tags=["python", "testing", "dev"],
            canonical_url="https://example.com/article",
        )
        m = Medium("token")
        result = m.format_for_manual(article)

        assert "# My Article" in result
        assert "*A brief description*" in result
        assert "Full body content here." in result
        assert "Tags: python, testing, dev" in result
        assert "Originally published at: https://example.com/article" in result

    def test_format_for_manual_minimal(self):
        article = Article(title="Simple", body="Just body")
        m = Medium("token")
        result = m.format_for_manual(article)

        assert "# Simple" in result
        assert "Just body" in result
        assert "Tags:" not in result
        assert "Originally published" not in result

    def test_format_for_manual_limits_tags(self):
        article = Article(
            title="T", body="B",
            tags=["one", "two", "three", "four", "five", "six"],
        )
        m = Medium("token")
        result = m.format_for_manual(article)

        assert "one" in result
        assert "five" in result
        assert "six" not in result

    @patch("crier.platforms.medium.requests.get")
    def test_get_user_id_success(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"data": {"id": "user_abc123"}}),
        )

        m = Medium("token")
        user_id = m._get_user_id()

        assert user_id == "user_abc123"

    @patch("crier.platforms.medium.requests.get")
    def test_get_user_id_cached(self, mock_get):
        """User ID is cached after first fetch."""
        m = Medium("token")
        m._user_id = "cached_id"
        user_id = m._get_user_id()

        assert user_id == "cached_id"
        mock_get.assert_not_called()

    @patch("crier.platforms.medium.requests.get")
    def test_get_user_id_failure(self, mock_get):
        mock_get.return_value = Mock(status_code=401)

        m = Medium("bad_token")
        user_id = m._get_user_id()

        assert user_id is None

    @patch("crier.platforms.medium.requests.post")
    @patch("crier.platforms.medium.requests.get")
    def test_publish_success(self, mock_get, mock_post, sample_article):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"data": {"id": "user1"}}),
        )
        mock_post.return_value = Mock(
            status_code=201,
            json=Mock(return_value={
                "data": {
                    "id": "medium_post_1",
                    "url": "https://medium.com/@user/test-article-abc123",
                }
            }),
        )

        m = Medium("token")
        result = m.publish(sample_article)

        assert result.success is True
        assert result.article_id == "medium_post_1"
        assert "medium.com" in result.url

    @patch("crier.platforms.medium.requests.post")
    @patch("crier.platforms.medium.requests.get")
    def test_publish_sends_correct_payload(self, mock_get, mock_post, sample_article):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"data": {"id": "user1"}}),
        )
        mock_post.return_value = Mock(
            status_code=201,
            json=Mock(return_value={"data": {"id": "1", "url": "https://medium.com/x"}}),
        )

        m = Medium("token")
        m.publish(sample_article)

        call_kwargs = mock_post.call_args
        json_data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert json_data["title"] == sample_article.title
        assert json_data["contentFormat"] == "markdown"
        assert json_data["content"] == sample_article.body
        assert json_data["publishStatus"] == "public"
        assert json_data["tags"] == sample_article.tags[:5]
        assert json_data["canonicalUrl"] == sample_article.canonical_url

    @patch("crier.platforms.medium.requests.post")
    @patch("crier.platforms.medium.requests.get")
    def test_publish_draft(self, mock_get, mock_post):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"data": {"id": "user1"}}),
        )
        mock_post.return_value = Mock(
            status_code=201,
            json=Mock(return_value={"data": {"id": "1", "url": "https://medium.com/x"}}),
        )

        article = Article(title="Draft", body="Content", published=False)
        m = Medium("token")
        m.publish(article)

        call_kwargs = mock_post.call_args
        json_data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert json_data["publishStatus"] == "draft"

    @patch("crier.platforms.medium.requests.get")
    def test_publish_auth_failure(self, mock_get, sample_article):
        mock_get.return_value = Mock(status_code=401)

        m = Medium("bad_token")
        result = m.publish(sample_article)

        assert result.success is False
        assert "authenticate" in result.error.lower() or "Failed" in result.error

    @patch("crier.platforms.medium.requests.post")
    @patch("crier.platforms.medium.requests.get")
    def test_publish_api_error(self, mock_get, mock_post, sample_article):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"data": {"id": "user1"}}),
        )
        mock_post.return_value = Mock(status_code=400, text="Bad request")

        m = Medium("token")
        result = m.publish(sample_article)

        assert result.success is False
        assert "400" in result.error

    def test_update_not_supported(self, sample_article):
        m = Medium("token")
        result = m.update("123", sample_article)

        assert result.success is False
        assert "not support" in result.error.lower() or "does not support" in result.error

    def test_list_articles_returns_empty(self):
        m = Medium("token")
        assert m.list_articles() == []

    def test_get_article_returns_none(self):
        m = Medium("token")
        assert m.get_article("123") is None

    def test_delete_not_supported(self):
        m = Medium("token")
        result = m.delete("123")

        assert result.success is False
        assert "does not support" in result.error


class TestButtondown:
    """Tests for Buttondown platform."""

    def test_buttondown_properties(self):
        bd = Buttondown("api_key_123")
        assert bd.name == "buttondown"
        assert bd.headers["Authorization"] == "Token api_key_123"

    @patch("crier.platforms.buttondown.requests.post")
    def test_publish_success(self, mock_post, sample_article):
        mock_post.return_value = Mock(
            status_code=201,
            json=Mock(return_value={"id": "email_abc"}),
        )

        bd = Buttondown("api_key")
        result = bd.publish(sample_article)

        assert result.success is True
        assert result.article_id == "email_abc"
        assert result.url == "https://buttondown.email/archive/email_abc"

    @patch("crier.platforms.buttondown.requests.post")
    def test_publish_success_200(self, mock_post, sample_article):
        """Buttondown can return 200 or 201 on publish success."""
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"id": "email_def"}),
        )

        bd = Buttondown("api_key")
        result = bd.publish(sample_article)

        assert result.success is True

    @patch("crier.platforms.buttondown.requests.post")
    def test_publish_sends_correct_payload(self, mock_post, sample_article):
        mock_post.return_value = Mock(
            status_code=201,
            json=Mock(return_value={"id": "1"}),
        )

        bd = Buttondown("api_key")
        bd.publish(sample_article)

        call_kwargs = mock_post.call_args
        json_data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert json_data["subject"] == sample_article.title
        assert json_data["body"] == sample_article.body
        assert json_data["status"] == "published"
        assert json_data["description"] == sample_article.description

    @patch("crier.platforms.buttondown.requests.post")
    def test_publish_draft(self, mock_post):
        article = Article(title="Newsletter", body="Content", published=False)
        mock_post.return_value = Mock(
            status_code=201,
            json=Mock(return_value={"id": "d1"}),
        )

        bd = Buttondown("api_key")
        bd.publish(article)

        call_kwargs = mock_post.call_args
        json_data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert json_data["status"] == "draft"

    @patch("crier.platforms.buttondown.requests.post")
    def test_publish_no_id_in_response(self, mock_post, sample_article):
        """If id is missing from response, url should be None."""
        mock_post.return_value = Mock(
            status_code=201,
            json=Mock(return_value={}),
        )

        bd = Buttondown("api_key")
        result = bd.publish(sample_article)

        assert result.success is True
        assert result.article_id is None
        assert result.url is None

    @patch("crier.platforms.buttondown.requests.post")
    def test_publish_failure(self, mock_post, sample_article):
        mock_post.return_value = Mock(status_code=422, text="Invalid email")

        bd = Buttondown("api_key")
        result = bd.publish(sample_article)

        assert result.success is False
        assert "422" in result.error

    @patch("crier.platforms.buttondown.requests.patch")
    def test_update_success(self, mock_patch, sample_article):
        mock_patch.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"id": "email_abc"}),
        )

        bd = Buttondown("api_key")
        result = bd.update("email_abc", sample_article)

        assert result.success is True
        assert result.article_id == "email_abc"
        assert "buttondown.email" in result.url

    @patch("crier.platforms.buttondown.requests.patch")
    def test_update_failure(self, mock_patch, sample_article):
        mock_patch.return_value = Mock(status_code=404, text="Not found")

        bd = Buttondown("api_key")
        result = bd.update("nonexistent", sample_article)

        assert result.success is False
        assert "404" in result.error

    @patch("crier.platforms.buttondown.requests.get")
    def test_list_articles_success(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "results": [
                    {"id": "e1", "subject": "Newsletter #1", "status": "published"},
                    {"id": "e2", "subject": "Newsletter #2", "status": "draft"},
                ]
            }),
        )

        bd = Buttondown("api_key")
        articles = bd.list_articles(limit=5)

        assert len(articles) == 2
        assert articles[0]["id"] == "e1"
        assert articles[0]["title"] == "Newsletter #1"
        assert articles[0]["published"] is True
        assert articles[1]["published"] is False
        assert "buttondown.email/archive/e1" in articles[0]["url"]

    @patch("crier.platforms.buttondown.requests.get")
    def test_list_articles_as_list_response(self, mock_get):
        """Buttondown may return a plain list instead of paginated results."""
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value=[
                {"id": "e1", "subject": "Newsletter #1", "status": "published"},
            ]),
        )

        bd = Buttondown("api_key")
        articles = bd.list_articles()

        assert len(articles) == 1

    @patch("crier.platforms.buttondown.requests.get")
    def test_list_articles_api_error(self, mock_get):
        mock_get.return_value = Mock(status_code=401, text="Unauthorized")

        bd = Buttondown("api_key")
        articles = bd.list_articles()

        assert articles == []

    @patch("crier.platforms.buttondown.requests.get")
    def test_get_article_success(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"id": "e1", "subject": "Test", "body": "Content"}),
        )

        bd = Buttondown("api_key")
        article = bd.get_article("e1")

        assert article is not None
        assert article["id"] == "e1"

    @patch("crier.platforms.buttondown.requests.get")
    def test_get_article_not_found(self, mock_get):
        mock_get.return_value = Mock(status_code=404)

        bd = Buttondown("api_key")
        article = bd.get_article("nonexistent")

        assert article is None

    @patch("crier.platforms.buttondown.requests.delete")
    def test_delete_success_204(self, mock_delete):
        mock_delete.return_value = Mock(status_code=204)

        bd = Buttondown("api_key")
        result = bd.delete("e1")

        assert result.success is True

    @patch("crier.platforms.buttondown.requests.delete")
    def test_delete_success_200(self, mock_delete):
        mock_delete.return_value = Mock(status_code=200)

        bd = Buttondown("api_key")
        result = bd.delete("e1")

        assert result.success is True

    @patch("crier.platforms.buttondown.requests.delete")
    def test_delete_failure(self, mock_delete):
        mock_delete.return_value = Mock(status_code=403, text="Forbidden")

        bd = Buttondown("api_key")
        result = bd.delete("e1")

        assert result.success is False
        assert "403" in result.error


class TestTelegram:
    """Tests for Telegram platform."""

    def test_telegram_properties(self):
        tg = Telegram("123456:ABC-DEF:@mychannel")
        assert tg.name == "telegram"
        assert tg.max_content_length == 4096

    def test_api_key_parsing(self):
        tg = Telegram("123456:ABC-DEF:@mychannel")
        assert tg.bot_token == "123456:ABC-DEF"
        assert tg.chat_id == "@mychannel"
        assert tg.base_url == "https://api.telegram.org/bot123456:ABC-DEF"

    def test_invalid_api_key_no_colon(self):
        with pytest.raises(ValueError) as exc:
            Telegram("noformat")
        assert "bot_token:chat_id" in str(exc.value)

    def test_format_message_full(self):
        article = Article(
            title="New Post",
            body="Full body here",
            description="Short description",
            canonical_url="https://example.com/post",
            tags=["python", "web-dev", "testing"],
        )
        tg = Telegram("bot_token:chat_id")
        msg = tg._format_message(article)

        assert "*New Post*" in msg
        assert "Short description" in msg
        assert "https://example.com/post" in msg
        assert "#python" in msg
        assert "#web_dev" in msg  # Hyphens converted to underscores
        assert "#testing" in msg

    def test_format_message_minimal(self):
        article = Article(title="Simple", body="Body")
        tg = Telegram("bot_token:chat_id")
        msg = tg._format_message(article)

        assert "*Simple*" in msg
        assert "#" not in msg  # No tags

    @patch("crier.platforms.telegram.requests.post")
    def test_publish_success_public_channel(self, mock_post):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "ok": True,
                "result": {
                    "message_id": 42,
                    "chat": {"username": "mychannel"},
                }
            }),
        )

        article = Article(title="News", body="Breaking news")
        tg = Telegram("bot_token:@mychannel")
        result = tg.publish(article)

        assert result.success is True
        assert result.article_id == "42"
        assert result.url == "https://t.me/mychannel/42"

    @patch("crier.platforms.telegram.requests.post")
    def test_publish_success_private_channel(self, mock_post):
        """Private channels have no username, so URL should be None."""
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "ok": True,
                "result": {
                    "message_id": 99,
                    "chat": {},  # No username for private channels
                }
            }),
        )

        article = Article(title="Private", body="Secret content")
        tg = Telegram("bot_token:-100123456")
        result = tg.publish(article)

        assert result.success is True
        assert result.article_id == "99"
        assert result.url is None

    @patch("crier.platforms.telegram.requests.post")
    def test_publish_telegram_error(self, mock_post):
        """Telegram returns 200 but ok=false."""
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "ok": False,
                "description": "Bad Request: chat not found",
            }),
        )

        article = Article(title="Test", body="Content")
        tg = Telegram("bot_token:bad_chat")
        result = tg.publish(article)

        assert result.success is False
        assert "chat not found" in result.error

    @patch("crier.platforms.telegram.requests.post")
    def test_publish_http_error(self, mock_post):
        mock_post.return_value = Mock(status_code=401, text="Unauthorized")

        article = Article(title="Test", body="Content")
        tg = Telegram("bad_token:chat_id")
        result = tg.publish(article)

        assert result.success is False
        assert "401" in result.error

    def test_publish_content_too_long(self):
        """Message exceeding 4096 chars should fail."""
        # _format_message uses title, description, URL, tags -- not body
        # So we need enough content in those fields to exceed 4096
        article = Article(
            title="A" * 3900,
            body="ignored body",
            description="D" * 200,
            canonical_url="https://example.com/very-long-url",
            tags=["python", "testing", "web"],
        )
        tg = Telegram("bot_token:chat_id")
        result = tg.publish(article)

        assert result.success is False
        assert "too long" in result.error.lower()

    @patch("crier.platforms.telegram.requests.post")
    def test_update_success(self, mock_post):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "ok": True,
                "result": {
                    "message_id": 42,
                    "chat": {"username": "mychannel"},
                }
            }),
        )

        article = Article(title="Updated Title", body="Updated content")
        tg = Telegram("bot_token:@mychannel")
        result = tg.update("42", article)

        assert result.success is True
        assert result.article_id == "42"
        assert result.url == "https://t.me/mychannel/42"

    @patch("crier.platforms.telegram.requests.post")
    def test_update_telegram_error(self, mock_post):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "ok": False,
                "description": "Bad Request: message to edit not found",
            }),
        )

        article = Article(title="T", body="B")
        tg = Telegram("bot_token:chat_id")
        result = tg.update("999", article)

        assert result.success is False
        assert "message to edit not found" in result.error

    @patch("crier.platforms.telegram.requests.post")
    def test_update_http_error(self, mock_post):
        mock_post.return_value = Mock(status_code=400, text="Bad Request")

        article = Article(title="T", body="B")
        tg = Telegram("bot_token:chat_id")
        result = tg.update("42", article)

        assert result.success is False
        assert "400" in result.error

    def test_list_articles_returns_empty(self):
        tg = Telegram("bot_token:chat_id")
        assert tg.list_articles() == []

    def test_get_article_returns_none(self):
        tg = Telegram("bot_token:chat_id")
        assert tg.get_article("42") is None

    @patch("crier.platforms.telegram.requests.post")
    def test_delete_success(self, mock_post):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"ok": True}),
        )

        tg = Telegram("bot_token:chat_id")
        result = tg.delete("42")

        assert result.success is True
        assert result.platform == "telegram"

    @patch("crier.platforms.telegram.requests.post")
    def test_delete_telegram_error(self, mock_post):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "ok": False,
                "description": "Bad Request: message can't be deleted",
            }),
        )

        tg = Telegram("bot_token:chat_id")
        result = tg.delete("42")

        assert result.success is False
        assert "can't be deleted" in result.error

    @patch("crier.platforms.telegram.requests.post")
    def test_delete_http_error(self, mock_post):
        mock_post.return_value = Mock(status_code=403, text="Forbidden")

        tg = Telegram("bot_token:chat_id")
        result = tg.delete("42")

        assert result.success is False
        assert "403" in result.error


class TestDiscord:
    """Tests for Discord platform."""

    WEBHOOK_URL = "https://discord.com/api/webhooks/123456789/abcdef_token"

    def test_discord_properties(self):
        d = Discord(self.WEBHOOK_URL)
        assert d.name == "discord"
        assert d.max_content_length == 4096
        assert d.webhook_url == self.WEBHOOK_URL

    def test_invalid_webhook_url(self):
        with pytest.raises(ValueError) as exc:
            Discord("https://example.com/not-a-webhook")
        assert "webhook URL" in str(exc.value)

    def test_create_embed_full(self):
        article = Article(
            title="New Release",
            body="Full body here",
            description="Check out our new release!",
            canonical_url="https://example.com/release",
            tags=["release", "python", "v2"],
        )
        d = Discord(self.WEBHOOK_URL)
        embed = d._create_embed(article)

        assert embed["title"] == "New Release"
        assert embed["description"] == "Check out our new release!"
        assert embed["url"] == "https://example.com/release"
        assert embed["color"] == 5814783
        assert "#release" in embed["footer"]["text"]
        assert "#python" in embed["footer"]["text"]

    def test_create_embed_minimal(self):
        article = Article(title="Simple", body="Body")
        d = Discord(self.WEBHOOK_URL)
        embed = d._create_embed(article)

        assert embed["title"] == "Simple"
        assert "description" not in embed
        assert "url" not in embed
        assert "footer" not in embed

    @patch("crier.platforms.discord.requests.post")
    def test_publish_success(self, mock_post, sample_article):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"id": "msg_123456"}),
        )

        d = Discord(self.WEBHOOK_URL)
        result = d.publish(sample_article)

        assert result.success is True
        assert result.article_id == "msg_123456"
        assert result.url is None  # Webhooks don't return URLs
        assert result.platform == "discord"

    @patch("crier.platforms.discord.requests.post")
    def test_publish_with_canonical_url(self, mock_post):
        """Articles with canonical_url get a different content prefix."""
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"id": "msg_1"}),
        )

        article = Article(
            title="My Post",
            body="Content",
            canonical_url="https://example.com/post",
        )
        d = Discord(self.WEBHOOK_URL)
        d.publish(article)

        call_kwargs = mock_post.call_args
        json_data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "New post" in json_data["content"]

    @patch("crier.platforms.discord.requests.post")
    def test_publish_without_canonical_url(self, mock_post):
        mock_post.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"id": "msg_2"}),
        )

        article = Article(title="My Post", body="Content")
        d = Discord(self.WEBHOOK_URL)
        d.publish(article)

        call_kwargs = mock_post.call_args
        json_data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "**My Post**" in json_data["content"]
        assert "New post" not in json_data["content"]

    @patch("crier.platforms.discord.requests.post")
    def test_publish_failure(self, mock_post, sample_article):
        mock_post.return_value = Mock(status_code=400, text="Bad Request")

        d = Discord(self.WEBHOOK_URL)
        result = d.publish(sample_article)

        assert result.success is False
        assert "400" in result.error

    def test_publish_description_too_long(self):
        """Embed description exceeding 4096 chars should fail."""
        article = Article(
            title="Title",
            body="body",
            description="D" * 5000,
        )
        d = Discord(self.WEBHOOK_URL)
        result = d.publish(article)

        assert result.success is False
        assert "too long" in result.error.lower()

    @patch("crier.platforms.discord.requests.patch")
    def test_update_success(self, mock_patch, sample_article):
        mock_patch.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"id": "msg_123"}),
        )

        d = Discord(self.WEBHOOK_URL)
        result = d.update("msg_123", sample_article)

        assert result.success is True
        assert result.article_id == "msg_123"
        assert result.url is None

    @patch("crier.platforms.discord.requests.patch")
    def test_update_without_canonical_url(self, mock_patch):
        """Update message without canonical_url uses plain title format."""
        mock_patch.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"id": "msg_456"}),
        )

        article = Article(title="Plain Title", body="Content")
        d = Discord(self.WEBHOOK_URL)
        result = d.update("msg_456", article)

        assert result.success is True
        call_kwargs = mock_patch.call_args
        json_data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "**Plain Title**" in json_data["content"]
        assert "New post" not in json_data["content"]

    @patch("crier.platforms.discord.requests.patch")
    def test_update_failure(self, mock_patch, sample_article):
        mock_patch.return_value = Mock(status_code=404, text="Unknown Message")

        d = Discord(self.WEBHOOK_URL)
        result = d.update("bad_msg", sample_article)

        assert result.success is False
        assert "404" in result.error

    def test_list_articles_returns_empty(self):
        d = Discord(self.WEBHOOK_URL)
        assert d.list_articles() == []

    @patch("crier.platforms.discord.requests.get")
    def test_get_article_success(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"id": "msg_123", "content": "Hello"}),
        )

        d = Discord(self.WEBHOOK_URL)
        article = d.get_article("msg_123")

        assert article is not None
        assert article["id"] == "msg_123"

    @patch("crier.platforms.discord.requests.get")
    def test_get_article_not_found(self, mock_get):
        mock_get.return_value = Mock(status_code=404)

        d = Discord(self.WEBHOOK_URL)
        article = d.get_article("nonexistent")

        assert article is None

    @patch("crier.platforms.discord.requests.delete")
    def test_delete_success(self, mock_delete):
        mock_delete.return_value = Mock(status_code=204)

        d = Discord(self.WEBHOOK_URL)
        result = d.delete("msg_123")

        assert result.success is True
        assert result.platform == "discord"

    @patch("crier.platforms.discord.requests.delete")
    def test_delete_failure(self, mock_delete):
        mock_delete.return_value = Mock(status_code=404, text="Unknown Message")

        d = Discord(self.WEBHOOK_URL)
        result = d.delete("bad_msg")

        assert result.success is False
        assert "404" in result.error
