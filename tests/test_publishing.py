from unittest.mock import patch

from crier.platforms.base import Article
from crier.publishing import PublishOutcome, prepare_publish


def _article():
    return Article(
        title="Hello World",
        body="A" * 50,
        description="desc",
        tags=["python"],
        canonical_url="https://example.com/post/hello/",
    )


@patch("crier.publishing.parse_markdown_file")
@patch("crier.publishing.get_api_key", return_value="real-key")
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_prepare_publish_api_mode_no_rewrite(mode, key, parse):
    parse.return_value = _article()
    plan = prepare_publish("post.md", "devto")
    assert plan.error is None
    assert plan.mode == "api"
    assert plan.api_key == "real-key"
    assert plan.article.title == "Hello World"
    assert plan.rewritten is False
    assert plan.posted_content is None


@patch("crier.publishing.get_platform_mode", return_value="manual")
def test_prepare_publish_rejects_non_api_mode(mode):
    plan = prepare_publish("post.md", "twitter")
    assert plan.error is not None
    assert "manual" in plan.error
    assert plan.article is None


@patch("crier.publishing.get_api_key", return_value=None)
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_prepare_publish_missing_key(mode, key):
    plan = prepare_publish("post.md", "devto")
    assert plan.error is not None
    assert "No API key" in plan.error


@patch("crier.publishing.parse_markdown_file")
@patch("crier.publishing.get_api_key", return_value="real-key")
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_prepare_publish_explicit_rewrite(mode, key, parse):
    parse.return_value = _article()
    plan = prepare_publish("post.md", "bluesky", rewrite_content="short take")
    assert plan.rewritten is True
    assert plan.posted_content == "short take"
    assert plan.article.body == "short take"
    assert plan.article.is_rewrite is True


# PublishOutcome is imported above for use in Task 2 tests; verify importable
def test_publish_outcome_importable():
    """PublishOutcome is importable from crier.publishing."""
    assert PublishOutcome is not None
