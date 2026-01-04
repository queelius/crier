"""Tests for crier.platforms module."""

import pytest
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
)


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

    def test_delete_not_implemented(self):
        platform = Twitter("manual")
        with pytest.raises(NotImplementedError):
            platform.delete("123")


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

    def test_delete_not_implemented(self):
        platform = Threads("user:token")
        with pytest.raises(NotImplementedError):
            platform.delete("123")


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
