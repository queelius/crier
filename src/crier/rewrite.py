"""Auto-rewrite logic for platform content adaptation.

Handles the LLM retry loop, truncation fallback, and Article construction
for auto-rewritten content. Used by both publish() and audit() in cli.py.
"""

from dataclasses import dataclass

from .platforms.base import Article
from .utils import truncate_at_sentence


@dataclass
class AutoRewriteResult:
    """Result of an auto-rewrite attempt."""

    success: bool
    article: Article | None = None
    rewrite_text: str | None = None
    error: str | None = None


def auto_rewrite_for_platform(
    article: Article,
    platform_name: str,
    max_len: int,
    llm_provider,
    *,
    retry_count: int = 0,
    truncate_fallback: bool = False,
    silent: bool = False,
    console=None,
) -> AutoRewriteResult:
    """Run LLM auto-rewrite with retry loop and optional truncation.

    Args:
        article: The source article to rewrite.
        platform_name: Target platform name (e.g., "bluesky").
        max_len: Maximum character length for the platform.
        llm_provider: Configured LLM provider instance.
        retry_count: Number of retries if output exceeds limit.
        truncate_fallback: If True, truncate at sentence boundary
            when all retries are exhausted.
        silent: Suppress console output.
        console: Rich Console instance for output (required if
            not silent).

    Returns:
        AutoRewriteResult with success status and rewritten article
        or error message.
    """
    from .llm import LLMProviderError

    if not silent and console:
        console.print(
            f"[dim]Content too long for {platform_name} "
            f"({len(article.body)} > {max_len})[/dim]"
        )
        retry_info = (
            f" (max {retry_count} retries)" if retry_count else ""
        )
        console.print(
            f"[dim]Generating auto-rewrite using "
            f"{llm_provider.model}{retry_info}...[/dim]"
        )

    try:
        rewrite_result = None
        prev_text = None
        last_length = None
        max_attempts = retry_count + 1

        for attempt in range(max_attempts):
            if attempt > 0 and not silent and console:
                console.print(
                    f"[yellow]Retry {attempt}/{retry_count} "
                    f"(previous: {last_length}/{max_len} chars, "
                    f"{last_length - max_len} over)[/yellow]"
                )

            rewrite_result = llm_provider.rewrite(
                title=article.title,
                body=article.body,
                max_chars=max_len,
                platform=platform_name,
                previous_attempt=prev_text,
                previous_length=last_length,
            )

            last_length = len(rewrite_result.text)

            if last_length <= max_len:
                break

            prev_text = rewrite_result.text

        # Check final result
        final_text = rewrite_result.text

        if len(final_text) <= max_len:
            pct = len(final_text) * 100 // max_len
            if not silent and console:
                console.print(
                    f"[green]✓ Generated {len(final_text)}/{max_len} "
                    f"char rewrite ({pct}%)[/green]"
                )
            return AutoRewriteResult(
                success=True,
                article=_rewritten_article(article, final_text),
                rewrite_text=final_text,
            )

        if truncate_fallback:
            truncated = truncate_at_sentence(final_text, max_len)
            pct = len(truncated) * 100 // max_len
            if not silent and console:
                console.print(
                    f"[yellow]⚠ Truncated to {len(truncated)}/{max_len} "
                    f"chars ({pct}%)[/yellow]"
                )
            return AutoRewriteResult(
                success=True,
                article=_rewritten_article(article, truncated),
                rewrite_text=truncated,
            )

        # All retries failed, no truncate fallback
        return AutoRewriteResult(
            success=False,
            error=(
                f"Auto-rewrite still too long after {max_attempts} "
                f"attempt(s): {len(final_text)} chars (limit: {max_len}). "
                f"Use --auto-rewrite-retry or --auto-rewrite-truncate."
            ),
        )

    except LLMProviderError as e:
        return AutoRewriteResult(
            success=False,
            error=f"Auto-rewrite failed: {e}",
        )


def _rewritten_article(original: Article, new_body: str) -> Article:
    """Create a new Article with rewritten body, preserving metadata."""
    return Article(
        title=original.title,
        body=new_body,
        description=original.description,
        tags=original.tags,
        canonical_url=original.canonical_url,
        published=original.published,
        cover_image=original.cover_image,
    )
