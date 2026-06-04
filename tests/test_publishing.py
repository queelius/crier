from unittest.mock import MagicMock, patch

from crier.platforms.base import Article, PublishResult
from crier.publishing import PublishOutcome, prepare_publish, publish_one
from crier.rewrite import AutoRewriteResult


def _article(body_len=50):
    return Article(
        title="Hello World",
        body="A" * body_len,
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


@patch("crier.publishing.get_platform")
@patch("crier.publishing.parse_markdown_file")
@patch("crier.publishing.get_api_key", return_value="real-key")
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_publish_one_success(mode, key, parse, get_plat):
    parse.return_value = _article()
    inst = MagicMock()
    inst.publish.return_value = PublishResult(
        success=True, platform="devto", article_id="123",
        url="https://dev.to/x/123",
    )
    get_plat.return_value = lambda _key: inst
    outcome = publish_one("post.md", "devto")
    assert outcome.result.success is True
    assert outcome.result.article_id == "123"
    assert outcome.article.title == "Hello World"
    assert outcome.rewritten is False


@patch("crier.publishing.get_platform")
@patch("crier.publishing.parse_markdown_file")
@patch("crier.publishing.get_api_key", return_value="real-key")
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_publish_one_dry_run_does_not_call_publish(mode, key, parse, get_plat):
    parse.return_value = _article()
    inst = MagicMock()
    get_plat.return_value = lambda _key: inst
    outcome = publish_one("post.md", "devto", dry_run=True)
    assert outcome.result.success is True
    assert outcome.article is not None
    inst.publish.assert_not_called()


@patch("crier.publishing.get_platform_mode", return_value="manual")
def test_publish_one_propagates_prepare_error(mode):
    outcome = publish_one("post.md", "twitter")
    assert outcome.result.success is False
    assert "manual" in outcome.result.error


@patch("crier.publishing.auto_rewrite_for_platform")
@patch("crier.publishing.get_platform")
@patch("crier.publishing.parse_markdown_file")
@patch("crier.publishing.get_api_key", return_value="real-key")
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_prepare_publish_auto_rewrite_success(mode, key, parse, get_plat, auto_rw):
    """Auto-rewrite success path: body exceeds max_content_length, LLM rewrites it."""
    long_article = _article(body_len=500)
    parse.return_value = long_article

    rewritten_article = Article(
        title="Hello World",
        body="short",
        description="desc",
        tags=["python"],
        canonical_url="https://example.com/post/hello/",
        is_rewrite=True,
    )
    auto_rw.return_value = AutoRewriteResult(
        success=True,
        article=rewritten_article,
        rewrite_text="short",
    )

    inst = MagicMock()
    inst.max_content_length = 300
    get_plat.return_value = lambda _k: inst

    llm_provider = MagicMock()
    llm_provider.model = "gpt-4o-mini"

    plan = prepare_publish(
        "post.md", "bluesky",
        auto_rewrite=True, llm_provider=llm_provider,
    )

    assert plan.error is None
    assert plan.rewritten is True
    assert plan.posted_content == "short"
    assert plan.rewrite_author == "llm:gpt-4o-mini"
    assert plan.article.body == "short"


@patch("crier.publishing.auto_rewrite_for_platform")
@patch("crier.publishing.get_platform")
@patch("crier.publishing.parse_markdown_file")
@patch("crier.publishing.get_api_key", return_value="real-key")
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_publish_one_auto_rewrite_failure(mode, key, parse, get_plat, auto_rw):
    """Auto-rewrite failure path: LLM can't fit content; publish is not called."""
    parse.return_value = _article(body_len=500)

    auto_rw.return_value = AutoRewriteResult(
        success=False,
        error="too long after retries",
    )

    inst = MagicMock()
    inst.max_content_length = 300
    get_plat.return_value = lambda _k: inst

    llm_provider = MagicMock()
    llm_provider.model = "gpt-4o-mini"

    outcome = publish_one(
        "post.md", "bluesky",
        auto_rewrite=True, llm_provider=llm_provider,
    )

    assert outcome.result.success is False
    assert "too long" in outcome.result.error
    assert isinstance(outcome, PublishOutcome)
    inst.publish.assert_not_called()


@patch("crier.publishing.get_platform")
@patch("crier.publishing.parse_markdown_file")
@patch("crier.publishing.get_api_key", return_value="real-key")
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_publish_one_platform_exception_wrapped(mode, key, parse, get_plat):
    """Platform exceptions are caught and wrapped in a failed PublishResult."""
    parse.return_value = _article()

    inst = MagicMock()
    inst.publish.side_effect = RuntimeError("boom")
    get_plat.return_value = lambda _k: inst

    outcome = publish_one("post.md", "devto")

    assert outcome.result.success is False
    assert "boom" in outcome.result.error
    assert isinstance(outcome, PublishOutcome)
