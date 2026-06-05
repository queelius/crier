"""Single-source publish orchestration.

publish_one() is the one place that turns (file, platform, rewrite options)
into a published result. It performs no registry writes, no console output by
default, and no prompts, so it is unit-testable and reusable by dry-run and
preview. Callers own recording and interactive UX.

Scope: api-mode single-post publishing. Manual, import, and thread handling
stay in the interactive publish command; the backlog campaign does not use
them.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import get_api_key, get_platform_mode
from .converters import parse_markdown_file
from .platforms import get_platform
from .platforms.base import Article, PublishResult
from .rewrite import apply_rewrite, auto_rewrite_for_platform


@dataclass
class PublishPlan:
    """Resolved inputs for a publish, before the platform call.

    error is set (and the other fields may be partial) when the plan cannot
    be built, e.g. wrong mode, missing key, parse failure.
    """

    platform: str
    mode: str
    api_key: str | None
    article: Article | None
    rewritten: bool = False
    posted_content: str | None = None
    rewrite_author: str | None = None
    error: str | None = None


@dataclass
class PublishOutcome:
    """Result of publish_one: the platform result plus rewrite bookkeeping.

    article is the final Article actually sent (post-rewrite). Callers use
    rewritten/posted_content/rewrite_author when recording to the registry.
    """

    result: PublishResult
    article: Article | None
    rewritten: bool = False
    posted_content: str | None = None
    rewrite_author: str | None = None


def prepare_publish(
    file_path: str | Path,
    platform: str,
    *,
    rewrite_content: str | None = None,
    rewrite_author: str | None = None,
    auto_rewrite: bool = False,
    llm_provider=None,
    auto_rewrite_retry: int = 0,
    auto_rewrite_truncate: bool = False,
    draft: bool = False,
    silent: bool = True,
    console=None,
) -> PublishPlan:
    """Parse, resolve mode/key, and apply any rewrite. No network, no I/O.

    Returns a PublishPlan. On any precondition failure the returned plan has
    .error set and .article may be None.
    """
    mode = get_platform_mode(platform)
    if mode != "api":
        return PublishPlan(
            platform=platform, mode=mode, api_key=None, article=None,
            error=f"{platform} is in {mode} mode (not API)",
        )

    api_key = get_api_key(platform)
    if not api_key:
        return PublishPlan(
            platform=platform, mode=mode, api_key=None, article=None,
            error=f"No API key configured for {platform}",
        )

    try:
        article = parse_markdown_file(str(file_path))
    except Exception as e:
        return PublishPlan(
            platform=platform, mode=mode, api_key=api_key, article=None,
            error=f"Failed to parse {file_path}: {e}",
        )

    if not article.title:
        return PublishPlan(
            platform=platform, mode=mode, api_key=api_key, article=None,
            error="Article has no title",
        )

    if draft:
        article.published = False

    rewritten = False
    posted_content = None

    if rewrite_content:
        article = apply_rewrite(article, rewrite_content)
        rewritten = True
        posted_content = rewrite_content
    elif auto_rewrite and llm_provider:
        platform_obj = get_platform(platform)(api_key)
        max_len = platform_obj.max_content_length
        if max_len and len(article.body) > max_len:
            rw = auto_rewrite_for_platform(
                article, platform, max_len, llm_provider,
                retry_count=auto_rewrite_retry,
                truncate_fallback=auto_rewrite_truncate,
                silent=silent, console=console,
            )
            if not rw.success:
                return PublishPlan(
                    platform=platform, mode=mode, api_key=api_key,
                    article=article, error=rw.error,
                )
            article = rw.article
            rewritten = True
            posted_content = rw.rewrite_text
            if not rewrite_author:
                rewrite_author = f"llm:{llm_provider.model}"

    return PublishPlan(
        platform=platform, mode=mode, api_key=api_key, article=article,
        rewritten=rewritten, posted_content=posted_content,
        rewrite_author=rewrite_author,
    )


def publish_one(
    file_path: str | Path,
    platform: str,
    *,
    rewrite_content: str | None = None,
    rewrite_author: str | None = None,
    auto_rewrite: bool = False,
    llm_provider=None,
    auto_rewrite_retry: int = 0,
    auto_rewrite_truncate: bool = False,
    draft: bool = False,
    dry_run: bool = False,
    silent: bool = True,
    console=None,
) -> PublishOutcome:
    """Publish one file to one api-mode platform.

    Does NOT record to the registry, prompt, or (by default) print. Returns a
    PublishOutcome wrapping the PublishResult plus rewrite bookkeeping. On
    dry_run, prepares the article and returns a synthetic success result
    without calling the platform.
    """
    plan = prepare_publish(
        file_path, platform,
        rewrite_content=rewrite_content, rewrite_author=rewrite_author,
        auto_rewrite=auto_rewrite, llm_provider=llm_provider,
        auto_rewrite_retry=auto_rewrite_retry,
        auto_rewrite_truncate=auto_rewrite_truncate,
        draft=draft, silent=silent, console=console,
    )

    if plan.error:
        return PublishOutcome(
            result=PublishResult(success=False, platform=platform, error=plan.error),
            article=plan.article,
        )

    if dry_run:
        return PublishOutcome(
            result=PublishResult(success=True, platform=platform),
            article=plan.article, rewritten=plan.rewritten,
            posted_content=plan.posted_content, rewrite_author=plan.rewrite_author,
        )

    try:
        platform_obj = get_platform(platform)(plan.api_key)
        result = platform_obj.publish(plan.article)
    except Exception as e:
        result = PublishResult(success=False, platform=platform, error=str(e))

    return PublishOutcome(
        result=result, article=plan.article, rewritten=plan.rewritten,
        posted_content=plan.posted_content, rewrite_author=plan.rewrite_author,
    )
