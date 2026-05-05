"""Tests for the FediversePlatform base abstraction.

Tests focus on:
1. The base class itself (importable from ``_fediverse``, not registered).
2. Mastodon as a concrete subclass (preserves prior behavior).
3. Pleroma as a second concrete subclass (validates the abstraction).
4. Behavior shared across both subclasses (composition helpers,
   instance hostname handling, request flow with mocked requests).

Mocks target ``crier.platforms.base.requests.<method>`` because
``Platform.retry_request`` does ``getattr(requests, method.lower())(url, ...)``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from crier.platforms import PLATFORMS
from crier.platforms._fediverse import FediversePlatform
from crier.platforms.base import Article
from crier.platforms.mastodon import Mastodon
from crier.platforms.pleroma import Pleroma


# --- Fixtures ----------------------------------------------------------


@pytest.fixture
def mastodon():
    """Mastodon configured against its default instance."""
    return Mastodon("mastodon.social:tok")


@pytest.fixture
def pleroma():
    """Pleroma configured against a representative instance."""
    return Pleroma("pleroma.example.com:tok")


# --- Discovery and registration ----------------------------------------


def test_fediverse_base_class_not_registered():
    """The leading-underscore module keeps the base out of PLATFORMS."""
    assert "fediverse" not in PLATFORMS
    assert "fediverseplatform" not in PLATFORMS
    # But it IS importable for subclasses
    assert issubclass(Mastodon, FediversePlatform)
    assert issubclass(Pleroma, FediversePlatform)


def test_concrete_subclasses_registered():
    assert "mastodon" in PLATFORMS
    assert "pleroma" in PLATFORMS
    assert PLATFORMS["mastodon"] is Mastodon
    assert PLATFORMS["pleroma"] is Pleroma


def test_subclasses_share_same_base():
    """Both concrete classes inherit directly from FediversePlatform."""
    assert Mastodon.__bases__ == (FediversePlatform,)
    assert Pleroma.__bases__ == (FediversePlatform,)


def test_subclasses_inherit_capabilities():
    for cls in (Mastodon, Pleroma):
        assert cls.is_short_form is True
        assert cls.supports_threads is True
        assert cls.supports_stats is True


# --- Construction and instance handling --------------------------------


def test_mastodon_default_instance():
    m = Mastodon("token123")
    assert m.instance == "https://mastodon.social"
    assert m.access_token == "token123"


def test_mastodon_explicit_instance_via_colon_format():
    m = Mastodon("fosstodon.org:my_token")
    assert m.instance == "https://fosstodon.org"
    assert m.access_token == "my_token"


def test_mastodon_explicit_instance_via_argument():
    m = Mastodon("my_token", instance="hachyderm.io")
    assert m.instance == "https://hachyderm.io"
    assert m.access_token == "my_token"


def test_pleroma_requires_instance():
    """Pleroma has no canonical hostname; must error on bare token."""
    with pytest.raises(ValueError, match="requires an instance hostname"):
        Pleroma("bare_token")


def test_pleroma_instance_via_colon_format():
    p = Pleroma("pleroma.example.com:my_token")
    assert p.instance == "https://pleroma.example.com"
    assert p.access_token == "my_token"


def test_pleroma_instance_via_argument():
    p = Pleroma("my_token", instance="pleroma.example.com")
    assert p.instance == "https://pleroma.example.com"


def test_instance_url_normalizes_to_https():
    m = Mastodon("hachyderm.io:tok")
    assert m.instance.startswith("https://")


def test_authorization_header_set():
    m = Mastodon("mastodon.social:bearer_xyz")
    assert m.headers["Authorization"] == "Bearer bearer_xyz"
    assert m.headers["Content-Type"] == "application/json"


def test_api_key_with_http_scheme_uses_last_colon():
    """Self-hosted dev instances often run http:// with non-default ports.

    A naive split(":", 1) would split at the scheme's colon and produce a
    broken instance ("http") plus a token starting with "//"; the parser
    must recognize a scheme prefix and use the LAST colon as the token
    separator instead.
    """
    p = Pleroma("http://localhost:3000:devtok")
    assert p.instance == "http://localhost:3000"
    assert p.access_token == "devtok"


def test_api_key_with_https_scheme_uses_last_colon():
    p = Pleroma("https://my.pleroma.example:8443:tok123")
    assert p.instance == "https://my.pleroma.example:8443"
    assert p.access_token == "tok123"


# --- Per-subclass class attributes -------------------------------------


def test_mastodon_max_content_length():
    assert Mastodon.max_content_length == 500


def test_pleroma_max_content_length():
    assert Pleroma.max_content_length == 5000


def test_class_names_distinct():
    assert Mastodon.name == "mastodon"
    assert Pleroma.name == "pleroma"


# --- Composition helpers (no network) ----------------------------------


def test_compose_text_uses_rewrite_body(mastodon):
    article = Article(
        title="Title that should NOT appear",
        body="Custom rewrite body",
        canonical_url="https://example.com/post/",
        is_rewrite=True,
    )
    text = mastodon._compose_text(article)
    assert "Custom rewrite body" in text
    assert "Title that should NOT appear" not in text
    assert "https://example.com/post/" in text


def test_compose_text_auto_constructs_when_not_rewrite(mastodon):
    article = Article(
        title="My Post",
        body="The full long-form body that we ignore for fediverse posts.",
        description="A short description.",
        canonical_url="https://example.com/post/",
        tags=["python", "long-form-thinking"],
        is_rewrite=False,
    )
    text = mastodon._compose_text(article)
    assert "My Post" in text
    assert "A short description." in text
    assert "https://example.com/post/" in text
    # Hashtags strip dashes
    assert "#python" in text
    assert "#longformthinking" in text


def test_compose_text_caps_hashtags_at_five(mastodon):
    article = Article(
        title="X",
        body="full body unused for tag composition",
        tags=["a", "b", "c", "d", "e", "f", "g"],
    )
    text = mastodon._compose_text(article)
    for tag in "abcde":
        assert f"#{tag}" in text
    for tag in "fg":
        assert f"#{tag}" not in text


def test_strip_html_paragraph_breaks():
    out = FediversePlatform._strip_html("<p>One</p><p>Two</p>")
    assert out == "One\nTwo"


def test_strip_html_br_tag_to_newline():
    out = FediversePlatform._strip_html("Line A<br>Line B<br/>Line C")
    assert out == "Line A\nLine B\nLine C"


def test_strip_html_collapses_inline_whitespace():
    """Spaces within a paragraph collapse but newlines from <p>/<br> stay."""
    out = FediversePlatform._strip_html("<p>Hello   world</p><p>Bye</p>")
    assert out == "Hello world\nBye"


# --- Mocked-request behavior (publish flow) ----------------------------


@patch("crier.platforms.base.requests.post")
def test_publish_with_missing_id_returns_none_not_string(mock_post):
    """Misbehaving server returns 201 but no ``id`` field.

    The registry receives ``article_id`` as ``None``, never the literal
    string ``"None"``, which would silently pollute the publications
    table with garbage IDs that no platform call could ever resolve.
    """
    mock_resp = MagicMock(status_code=201)
    mock_resp.json.return_value = {"url": "https://mastodon.social/@u/x"}
    mock_post.return_value = mock_resp

    m = Mastodon("mastodon.social:tok")
    result = m.publish(Article(title="x", body="hello", is_rewrite=True))

    assert result.success
    assert result.article_id is None
    assert result.article_id != "None"


@patch("crier.platforms.base.requests.post")
def test_pleroma_publish_uses_pleroma_instance(mock_post, pleroma):
    """Verify Pleroma instance URL ends up in the request, not mastodon.social."""
    mock_resp = MagicMock(status_code=201)
    mock_resp.json.return_value = {
        "id": "abc123",
        "url": "https://pleroma.example.com/notice/abc123",
    }
    mock_post.return_value = mock_resp

    article = Article(title="x", body="hello", is_rewrite=True)
    result = pleroma.publish(article)

    assert result.success
    assert result.platform == "pleroma"
    # First positional arg to requests.post is the URL.
    url_arg = mock_post.call_args.args[0]
    assert "pleroma.example.com" in url_arg
    assert "mastodon.social" not in url_arg
    assert "/api/v1/statuses" in url_arg


@patch("crier.platforms.base.requests.post")
def test_mastodon_publish_uses_default_instance(mock_post):
    mock_resp = MagicMock(status_code=201)
    mock_resp.json.return_value = {"id": "1", "url": "https://mastodon.social/@u/1"}
    mock_post.return_value = mock_resp

    m = Mastodon("token_only")
    article = Article(title="x", body="hello", is_rewrite=True)
    m.publish(article)

    url_arg = mock_post.call_args.args[0]
    assert "mastodon.social" in url_arg


@patch("crier.platforms.base.requests.post")
def test_publish_respects_subclass_max_content_length(mock_post):
    """Pleroma allows 5000 chars where Mastodon would reject the same text."""
    long_body = "x" * 1000  # > 500 (Mastodon limit), < 5000 (Pleroma limit)

    mock_resp = MagicMock(status_code=201)
    mock_resp.json.return_value = {"id": "1", "url": "u"}
    mock_post.return_value = mock_resp

    p = Pleroma("p.example.com:tok")
    p.max_retries = 0  # Don't retry on mocked responses
    m = Mastodon("mastodon.social:tok")
    m.max_retries = 0

    article = Article(title="x", body=long_body, is_rewrite=True, canonical_url=None)

    # Pleroma should accept the long body
    p_result = p.publish(article)
    assert p_result.success, p_result.error

    # Mastodon should reject without making any HTTP call
    mock_post.reset_mock()
    m_result = m.publish(article)
    assert not m_result.success
    assert mock_post.call_count == 0


@patch("crier.platforms.base.requests.get")
def test_get_stats_returns_engagement_fields(mock_get, mastodon):
    """get_stats parses favourites/replies/reblogs from the status response."""
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "id": "x",
        "favourites_count": 12,
        "replies_count": 3,
        "reblogs_count": 5,
    }
    mock_get.return_value = mock_resp

    stats = mastodon.get_stats("x")
    assert stats is not None
    assert stats.likes == 12
    assert stats.comments == 3
    assert stats.reposts == 5


@patch("crier.platforms.base.requests.post")
def test_publish_thread_chains_replies(mock_post, mastodon):
    """Each post after the first carries in_reply_to_id from the previous."""
    responses = [
        MagicMock(status_code=201),
        MagicMock(status_code=201),
        MagicMock(status_code=201),
    ]
    responses[0].json.return_value = {"id": "1", "url": "u1"}
    responses[1].json.return_value = {"id": "2", "url": "u2"}
    responses[2].json.return_value = {"id": "3", "url": "u3"}
    mock_post.side_effect = responses

    result = mastodon.publish_thread(["one", "two", "three"])

    assert result.success
    assert result.post_ids == ["1", "2", "3"]
    # First call: no in_reply_to_id
    assert "in_reply_to_id" not in mock_post.call_args_list[0].kwargs.get("json", {})
    # Second call: replies to "1"
    assert mock_post.call_args_list[1].kwargs["json"]["in_reply_to_id"] == "1"
    # Third call: replies to "2"
    assert mock_post.call_args_list[2].kwargs["json"]["in_reply_to_id"] == "2"
