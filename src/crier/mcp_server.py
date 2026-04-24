"""MCP Server for crier: full cross-posting toolkit for Claude Code.

Exposes the crier registry, content discovery, validation, publishing,
and analytics as MCP tools. Designed for full CLI parity so Claude Code
can orchestrate cross-posting workflows entirely via MCP.

Usage:
    crier mcp            # Start stdio server (for Claude Code)
    crier mcp --http     # Start HTTP/SSE server (for testing)

Tools (17):
    Registry:
        crier_query         Search articles by section, platform, archived
        crier_missing       Find content not published to specified platforms
        crier_article       Get full article details by slug/URL/file
        crier_publications  List publications for a platform
        crier_record        Record a manual publication
        crier_failures      List failed publications
        crier_summary       Registry summary statistics
        crier_sql           Raw SELECT queries on registry DB

    Content:
        crier_search        Scan content files with metadata and filters
        crier_check         Pre-publish validation

    Actions:
        crier_publish       Publish a file to a platform (two-step confirmation)
        crier_delete        Delete from a platform (two-step confirmation)
        crier_archive       Set archived status

    Platform:
        crier_list_remote   Query live platform API
        crier_doctor        Validate API keys
        crier_stats         Get cached engagement stats
        crier_stats_refresh Fetch fresh stats from platform API
"""

import dataclasses
import json
import random
import secrets
import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="crier",
    instructions=(
        "Crier is a cross-posting tool that tracks blog content published to "
        "multiple platforms (devto, hashnode, bluesky, mastodon, etc.).\n\n"
        "Platform modes:\n"
        "- API: automatic posting (devto, hashnode, bluesky, mastodon)\n"
        "- import: user imports from canonical URL (medium)\n"
        "- paste: copy-paste mode (twitter, threads, linkedin)\n\n"
        "Short-form platforms (bluesky 300, mastodon 500, twitter 280, threads 500) "
        "need rewrites. Claude writes the rewrite and passes it via rewrite_content.\n\n"
        "Destructive operations (publish, delete) use two-step confirmation:\n"
        "1. Call without confirmation_token to get a preview and token\n"
        "2. Call again with the token to execute\n"
    ),
)


# ============================================================================
# Helpers
# ============================================================================


def _get_conn():
    """Get a connection to the registry DB."""
    from .registry import get_connection
    return get_connection()


def _validate_platform(name: str) -> str | None:
    """Validate a platform name. Returns error message or None if valid."""
    from .platforms import PLATFORMS
    if name not in PLATFORMS:
        available = ", ".join(sorted(PLATFORMS.keys()))
        return f"Unknown platform '{name}'. Available: {available}"
    return None


def _resolve_file(file_path: str) -> Path | None:
    """Resolve a file path against project root. Returns None if not found or not a file."""
    if not file_path:
        return None
    from .config import get_project_root
    p = Path(file_path)
    if p.is_absolute() and p.is_file():
        return p
    resolved = get_project_root() / p
    if resolved.is_file():
        return resolved
    return None


def _apply_rewrite(article, rewrite_content: str):
    """Return a new Article with body replaced by the rewrite content."""
    return dataclasses.replace(
        article,
        body=rewrite_content,
        is_rewrite=True,
    )


# ============================================================================
# Confirmation tokens (two-step for destructive ops)
# ============================================================================

_pending_ops: dict[str, dict] = {}
_TOKEN_TTL = 300  # 5 minutes


def _create_token(operation: str, details: dict) -> str:
    """Create a confirmation token for a pending operation."""
    # Clean expired tokens
    now = time.time()
    expired = [k for k, v in _pending_ops.items() if now - v["created_at"] > _TOKEN_TTL]
    for k in expired:
        del _pending_ops[k]

    token = secrets.token_urlsafe(16)
    _pending_ops[token] = {
        "operation": operation,
        "details": details,
        "created_at": now,
    }
    return token


def _consume_token(token: str, expected_op: str) -> dict | None:
    """Consume a confirmation token. Returns details or None if invalid/expired."""
    op = _pending_ops.pop(token, None)
    if not op:
        return None
    if time.time() - op["created_at"] > _TOKEN_TTL:
        return None
    if op["operation"] != expected_op:
        return None
    return op["details"]


# ============================================================================
# Registry Tools
# ============================================================================


@mcp.tool()
def crier_query(
    section: str | None = None,
    platform: str | None = None,
    archived: bool | None = None,
    limit: int = 50,
) -> dict:
    """Search articles in the registry.

    Filter by section (e.g., "post", "papers"), platform (e.g., "devto"),
    or archived status.

    Examples:
        crier_query()                              # all articles
        crier_query(section="post", limit=10)      # recent posts
        crier_query(platform="devto")              # articles on devto
        crier_query(archived=True)                 # archived articles
    """
    if platform:
        err = _validate_platform(platform)
        if err:
            return {"error": err}

    conn = _get_conn()
    conditions: list[str] = []
    params: list[Any] = []

    if section:
        conditions.append("a.section = ?")
        params.append(section)
    if archived is True:
        conditions.append("a.archived_at IS NOT NULL")
    elif archived is False:
        conditions.append("a.archived_at IS NULL")
    if platform:
        conditions.append(
            "EXISTS (SELECT 1 FROM publications p "
            "WHERE p.slug = a.slug AND p.platform = ? "
            "AND p.deleted_at IS NULL AND p.platform_id IS NOT NULL)"
        )
        params.append(platform)

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    rows = conn.execute(
        f"SELECT a.slug, a.title, a.canonical_url, a.source_file, a.section, "
        f"a.archived_at, a.created_at FROM articles a{where} "
        f"ORDER BY a.created_at DESC LIMIT ?",
        params,
    ).fetchall()

    results = []
    for r in rows:
        platforms = [
            p["platform"] for p in conn.execute(
                "SELECT platform FROM publications "
                "WHERE slug = ? AND deleted_at IS NULL AND platform_id IS NOT NULL",
                (r["slug"],),
            ).fetchall()
        ]
        results.append({
            "slug": r["slug"],
            "title": r["title"],
            "canonical_url": r["canonical_url"],
            "source_file": r["source_file"],
            "section": r["section"],
            "archived": r["archived_at"] is not None,
            "platforms": platforms,
            "publication_count": len(platforms),
        })

    return {"articles": results, "count": len(results)}


@mcp.tool()
def crier_missing(
    platforms: list[str],
    section: str | None = None,
    limit: int = 50,
) -> dict:
    """Find articles NOT published to the specified platforms.

    Returns articles missing from one or more of the listed platforms.

    Examples:
        crier_missing(platforms=["devto", "hashnode"])
        crier_missing(platforms=["bluesky"], section="post")
    """
    for p in platforms:
        err = _validate_platform(p)
        if err:
            return {"error": err}

    conn = _get_conn()
    conditions = ["a.archived_at IS NULL"]
    params: list[Any] = []

    if section:
        conditions.append("a.section = ?")
        params.append(section)

    where = f" WHERE {' AND '.join(conditions)}"

    rows = conn.execute(
        f"SELECT a.slug, a.title, a.canonical_url, a.source_file, a.section "
        f"FROM articles a{where} ORDER BY a.created_at DESC LIMIT ?",
        params + [limit],
    ).fetchall()

    results = []
    for r in rows:
        missing = []
        for plat in platforms:
            pub = conn.execute(
                "SELECT 1 FROM publications "
                "WHERE slug = ? AND platform = ? "
                "AND deleted_at IS NULL AND platform_id IS NOT NULL",
                (r["slug"], plat),
            ).fetchone()
            if not pub:
                missing.append(plat)

        if missing:
            results.append({
                "slug": r["slug"],
                "title": r["title"],
                "canonical_url": r["canonical_url"],
                "source_file": r["source_file"],
                "section": r["section"],
                "missing_platforms": missing,
            })

    return {"articles": results, "count": len(results)}


@mcp.tool()
def crier_article(key: str) -> dict:
    """Get full details for a specific article.

    The key can be a slug, canonical URL, or source file path.

    Examples:
        crier_article("code-without-purpose")
        crier_article("https://metafunctor.com/post/2026-02-25-code-without-purpose/")
        crier_article("content/post/2026-02-25-code-without-purpose/index.md")
    """
    from .registry import get_article, get_article_by_file

    article = get_article(key)
    if not article:
        result = get_article_by_file(key)
        if result:
            _, article = result

    if not article:
        return {"error": f"Article not found: {key}"}

    return article


@mcp.tool()
def crier_publications(platform: str) -> dict:
    """Get all publications for a specific platform.

    Examples:
        crier_publications("devto")
        crier_publications("bluesky")
    """
    err = _validate_platform(platform)
    if err:
        return {"error": err}

    from .registry import get_platform_publications
    pubs = get_platform_publications(platform)
    return {"platform": platform, "publications": pubs, "count": len(pubs)}


@mcp.tool()
def crier_record(
    title: str,
    platform: str,
    platform_id: str | None = None,
    url: str | None = None,
    canonical_url: str | None = None,
    source_file: str | None = None,
    rewritten: bool = False,
    rewrite_author: str | None = None,
    posted_content: str | None = None,
) -> dict:
    """Record a publication to the registry (manual tracking).

    Creates the article if it doesn't exist, then records the publication.

    Examples:
        crier_record(title="My Post", platform="devto", platform_id="123",
                     url="https://dev.to/user/my-post")
    """
    err = _validate_platform(platform)
    if err:
        return {"error": err}

    from .registry import record_publication
    record_publication(
        canonical_url=canonical_url or None,
        platform=platform,
        article_id=platform_id,
        url=url,
        title=title,
        source_file=source_file,
        rewritten=rewritten,
        rewrite_author=rewrite_author,
        posted_content=posted_content,
    )
    return {"success": True, "message": f"Recorded '{title}' on {platform}"}


@mcp.tool()
def crier_failures() -> dict:
    """List all publications with recorded failures.

    Returns failed publications with error details, useful for
    diagnosing issues and deciding what to retry.

    Examples:
        crier_failures()  # then retry with crier_publish
    """
    from .registry import get_failures
    failures = get_failures()
    return {"failures": failures, "count": len(failures)}


@mcp.tool()
def crier_summary() -> dict:
    """Get registry summary statistics.

    Returns total articles, counts by section and platform,
    and number of unposted articles.
    """
    conn = _get_conn()

    total = conn.execute("SELECT COUNT(*) as n FROM articles").fetchone()["n"]

    sections = conn.execute(
        "SELECT COALESCE(section, 'unknown') as s, COUNT(*) as n "
        "FROM articles GROUP BY s ORDER BY n DESC"
    ).fetchall()

    platforms = conn.execute(
        "SELECT platform, COUNT(*) as n FROM publications "
        "WHERE deleted_at IS NULL AND platform_id IS NOT NULL "
        "GROUP BY platform ORDER BY n DESC"
    ).fetchall()

    unposted = conn.execute(
        "SELECT COUNT(*) as n FROM articles a "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM publications p "
        "  WHERE p.slug = a.slug AND p.deleted_at IS NULL AND p.platform_id IS NOT NULL"
        ")"
    ).fetchone()["n"]

    return {
        "total_articles": total,
        "by_section": {r["s"]: r["n"] for r in sections},
        "by_platform": {r["platform"]: r["n"] for r in platforms},
        "unposted": unposted,
    }


@mcp.tool()
def crier_sql(query: str) -> dict:
    """Execute a read-only query on the registry database.

    Tables: articles, publications, stats, schema_version.

    Examples:
        crier_sql("SELECT slug, title FROM articles ORDER BY created_at DESC LIMIT 10")
        crier_sql("SELECT platform, COUNT(*) as n FROM publications GROUP BY platform")
        crier_sql("SELECT a.title, p.platform FROM articles a JOIN publications p ON a.slug = p.slug")
    """
    conn = _get_conn()
    try:
        conn.execute("SAVEPOINT crier_sql_guard")
        try:
            rows = conn.execute(query).fetchall()
            if not rows:
                return {"rows": [], "count": 0}
            columns = rows[0].keys()
            result = [dict(zip(columns, row)) for row in rows]
            return {"rows": result, "count": len(result)}
        finally:
            conn.execute("ROLLBACK TO crier_sql_guard")
            conn.execute("RELEASE crier_sql_guard")
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# Content Tools
# ============================================================================


@mcp.tool()
def crier_search(
    path: str | None = None,
    tags: list[str] | None = None,
    since: str | None = None,
    until: str | None = None,
    sample: int | None = None,
    limit: int = 50,
) -> dict:
    """Scan content files and return metadata.

    Discovers markdown files from configured content_paths. Filters by
    tags, date range, and random sampling.

    Examples:
        crier_search()                                  # all content
        crier_search(tags=["python"], since="1m")       # python posts, last month
        crier_search(since="2w", limit=10)              # last 2 weeks
        crier_search(sample=5)                          # random 5
    """
    from .utils import find_content_files, parse_date_filter, get_content_date, get_content_tags
    from .converters import parse_markdown_file

    try:
        files = find_content_files(path)
    except Exception as e:
        return {"error": f"Content discovery failed: {e}"}

    # Date filtering
    if since or until:
        try:
            since_dt = parse_date_filter(since) if since else None
            until_dt = parse_date_filter(until) if until else None
        except ValueError as e:
            return {"error": f"Invalid date filter: {e}"}

        filtered = []
        for f in files:
            content_date = get_content_date(f)
            if content_date is None:
                continue
            if content_date.tzinfo is not None:
                content_date = content_date.replace(tzinfo=None)
            if since_dt and content_date < since_dt:
                continue
            if until_dt and content_date > until_dt:
                continue
            filtered.append(f)
        files = filtered

    # Tag filtering
    if tags:
        tag_set = {t.lower().strip() for t in tags}
        files = [f for f in files if any(t in tag_set for t in get_content_tags(f))]

    # Sampling
    if sample and len(files) > sample:
        files = random.sample(files, sample)

    # Limit
    files = sorted(files)[:limit]

    # Collect metadata
    results = []
    for f in files:
        try:
            article = parse_markdown_file(str(f))
            if article and article.title:
                content_date = get_content_date(f)
                results.append({
                    "file": str(f),
                    "title": article.title,
                    "date": content_date.isoformat() if content_date else None,
                    "tags": article.tags or [],
                    "description": article.description,
                    "canonical_url": article.canonical_url,
                    "words": len(article.body.split()) if article.body else 0,
                })
        except Exception:
            continue

    return {"results": results, "count": len(results)}


@mcp.tool()
def crier_check(
    file_path: str,
    platforms: list[str] | None = None,
    check_links: bool = False,
) -> dict:
    """Validate a content file before publishing.

    Checks front matter, content quality, and platform-specific requirements.

    Examples:
        crier_check("content/post/my-article/index.md")
        crier_check("content/post/my-article/index.md", platforms=["bluesky", "devto"])
    """
    resolved = _resolve_file(file_path)
    if not resolved:
        return {"error": f"File not found: {file_path}"}

    if platforms:
        for p in platforms:
            err = _validate_platform(p)
            if err:
                return {"error": err}

    from .checker import check_file
    from .config import get_site_base_url, get_check_overrides

    report = check_file(
        str(resolved),
        platforms=platforms,
        site_base_url=get_site_base_url(),
        severity_overrides=get_check_overrides(),
        check_links=check_links,
    )

    findings = []
    for r in report.results:
        findings.append({
            "check": r.check_name,
            "severity": r.severity,
            "message": r.message,
            "platform": r.platform,
        })

    return {
        "file": str(resolved),
        "passed": report.passed,
        "has_errors": report.has_errors,
        "has_warnings": report.has_warnings,
        "findings": findings,
    }


# ============================================================================
# Action Tools (destructive, use confirmation tokens)
# ============================================================================


@mcp.tool()
def crier_publish(
    file_path: str,
    platform: str,
    dry_run: bool = False,
    rewrite_content: str | None = None,
    rewrite_author: str | None = None,
    confirmation_token: str | None = None,
) -> dict:
    """Publish a content file to a platform.

    Two-step confirmation: call without token to get a preview, then
    call again with the returned token to execute.

    For short-form platforms (bluesky, mastodon), pass rewrite_content
    with a condensed version. Crier appends the canonical URL automatically.

    Examples:
        # Step 1: preview
        crier_publish("content/post/my-article/index.md", "devto")
        # Step 2: execute
        crier_publish("content/post/my-article/index.md", "devto",
                      confirmation_token="abc123")
        # Dry run (no confirmation needed)
        crier_publish("content/post/my-article/index.md", "devto", dry_run=True)
        # With rewrite for short-form
        crier_publish("content/post/my-article/index.md", "bluesky",
                      rewrite_content="Interesting take on X...",
                      rewrite_author="claude-code")
    """
    from .converters import parse_markdown_file
    from .config import get_api_key, get_platform_mode
    from .platforms import get_platform
    from .registry import record_publication, record_failure, is_published

    # Step 2: token is the source of truth. Ignore caller args to prevent bypass.
    if confirmation_token:
        details = _consume_token(confirmation_token, "publish")
        if not details:
            return {"error": "Invalid or expired confirmation token. Request a new one."}
        file_path = details["file"]
        platform = details["platform"]
        rewrite_content = details.get("rewrite_content")
        rewrite_author = details.get("rewrite_author")

    # Validate platform and resolve file (used by both step 1 and step 2)
    err = _validate_platform(platform)
    if err:
        return {"error": err}

    resolved = _resolve_file(file_path)
    if not resolved:
        return {"error": f"File not found: {file_path}"}

    # Parse article
    try:
        article = parse_markdown_file(str(resolved))
    except Exception as e:
        return {"error": f"Failed to parse {file_path}: {e}"}

    if not article.title:
        return {"error": "Article has no title"}

    # Check API key and mode
    api_key = get_api_key(platform)
    if not api_key:
        return {"error": f"No API key configured for {platform}"}

    mode = get_platform_mode(platform)
    if mode != "api":
        return {"error": f"{platform} is in {mode} mode (not API). Use CLI for manual/import."}

    # Apply rewrite if provided
    is_rewritten = bool(rewrite_content)
    posted_content = rewrite_content
    if rewrite_content:
        article = _apply_rewrite(article, rewrite_content)

    # Build preview
    preview = {
        "file": str(resolved),
        "title": article.title,
        "platform": platform,
        "canonical_url": article.canonical_url,
        "is_rewrite": is_rewritten,
        "body_length": len(article.body) if article.body else 0,
        "already_published": is_published(
            article.canonical_url or "", platform
        ) if article.canonical_url else False,
    }

    if dry_run:
        return {"dry_run": True, "preview": preview}

    # Step 1: no token yet -> snapshot args into token and return preview
    if not confirmation_token:
        token = _create_token("publish", {
            "file": str(resolved), "platform": platform,
            "rewrite_content": rewrite_content, "rewrite_author": rewrite_author,
        })
        return {
            "confirmation_required": True,
            "preview": preview,
            "confirmation_token": token,
            "message": f"Call again with confirmation_token to publish '{article.title}' to {platform}",
        }

    # Step 2: execute publish
    try:
        platform_obj = get_platform(platform)(api_key)
        result = platform_obj.publish(article)
    except Exception as e:
        if article.canonical_url:
            record_failure(article.canonical_url, platform, str(e), article.title, str(resolved))
        return {"error": f"Publish failed: {e}"}

    if not result.success:
        if article.canonical_url and result.error:
            record_failure(article.canonical_url, platform, result.error, article.title, str(resolved))
        return {"error": f"Publish failed: {result.error}"}

    if article.canonical_url:
        record_publication(
            canonical_url=article.canonical_url,
            platform=platform,
            article_id=result.article_id,
            url=result.url,
            title=article.title,
            source_file=str(resolved),
            rewritten=is_rewritten,
            rewrite_author=rewrite_author,
            posted_content=posted_content,
        )
    return {
        "success": True,
        "platform": platform,
        "title": article.title,
        "article_id": result.article_id,
        "url": result.url,
    }


@mcp.tool()
def crier_delete(
    key: str,
    platform: str | None = None,
    delete_all: bool = False,
    confirmation_token: str | None = None,
) -> dict:
    """Delete a publication from a platform.

    Two-step confirmation: call without token to see what would be deleted,
    then call with the returned token to execute.

    Examples:
        # Step 1: preview what would be deleted
        crier_delete("code-without-purpose", platform="devto")
        # Step 2: execute
        crier_delete("code-without-purpose", platform="devto",
                     confirmation_token="abc123")
        # Delete from all platforms
        crier_delete("code-without-purpose", delete_all=True)
    """
    from .registry import get_article, record_deletion, get_publication_id
    from .config import get_api_key, get_platform_mode
    from .platforms import get_platform

    # Step 2: token is the source of truth. Ignore caller args.
    if confirmation_token:
        details = _consume_token(confirmation_token, "delete")
        if not details:
            return {"error": "Invalid or expired confirmation token."}
        key = details["key"]
        target_platforms = details["platforms"]
        article = get_article(key)
        if not article:
            return {"error": f"Article not found: {key}"}
    else:
        if platform:
            err = _validate_platform(platform)
            if err:
                return {"error": err}

        if not platform and not delete_all:
            return {"error": "Specify platform or delete_all=True"}

        article = get_article(key)
        if not article:
            return {"error": f"Article not found: {key}"}

        # Determine platforms to delete from
        target_platforms = []
        if delete_all:
            target_platforms = [
                p for p, data in article.get("platforms", {}).items()
                if "deleted_at" not in data
            ]
        elif platform:
            pdata = article.get("platforms", {}).get(platform)
            if not pdata:
                return {"error": f"'{article['title']}' not published to {platform}"}
            if "deleted_at" in pdata:
                return {"error": f"'{article['title']}' on {platform} is already deleted"}
            target_platforms = [platform]

        if not target_platforms:
            return {"error": "Nothing to delete"}

        preview = {
            "title": article["title"],
            "slug": article["slug"],
            "platforms_to_delete": target_platforms,
        }

        # Step 1: snapshot into token and return preview
        token = _create_token("delete", {"key": key, "platforms": target_platforms})
        return {
            "confirmation_required": True,
            "preview": preview,
            "confirmation_token": token,
            "message": f"Call again with confirmation_token to delete from {target_platforms}",
        }

    # Step 2: execute deletions
    results = []
    for plat in target_platforms:
        canonical = article.get("canonical_url") or article["slug"]
        pub_id = get_publication_id(canonical, plat)
        api_key = get_api_key(plat)
        mode = get_platform_mode(plat)

        if mode != "api" or not api_key or not pub_id:
            record_deletion(canonical, plat)
            results.append({"platform": plat, "status": "marked_deleted"})
            continue

        try:
            platform_cls = get_platform(plat)
            platform_obj = platform_cls(api_key)
            del_result = platform_obj.delete(pub_id)
            record_deletion(canonical, plat)
            results.append({
                "platform": plat,
                "status": "deleted" if del_result.success else "marked_deleted",
                "error": del_result.error if not del_result.success else None,
            })
        except Exception as e:
            record_deletion(canonical, plat)
            results.append({"platform": plat, "status": "marked_deleted", "error": str(e)})

    return {"deleted": results}


@mcp.tool()
def crier_archive(key: str, archived: bool = True) -> dict:
    """Set the archived status of an article.

    Archived articles are excluded from crier_missing results.

    Examples:
        crier_archive("old-post-slug")                 # archive
        crier_archive("old-post-slug", archived=False)  # unarchive
    """
    from .registry import set_archived, get_article

    article = get_article(key)
    if not article:
        return {"error": f"Article not found: {key}"}

    success = set_archived(key, archived)
    verb = "archive" if archived else "unarchive"
    past = "archived" if archived else "unarchived"
    if success:
        return {"success": True, "message": f"'{article['title']}' {past}"}
    return {"error": f"Failed to {verb} '{key}'"}


# ============================================================================
# Platform Tools
# ============================================================================


@mcp.tool()
def crier_list_remote(platform: str, limit: int = 30) -> dict:
    """Query a platform's live API for published articles.

    Returns what's actually on the platform (not what's in the registry).
    Useful for finding posts that exist on the platform but aren't tracked.

    Examples:
        crier_list_remote("devto")
        crier_list_remote("bluesky", limit=50)
    """
    err = _validate_platform(platform)
    if err:
        return {"error": err}

    from .config import get_api_key, is_manual_mode_key, is_import_mode_key
    from .platforms import get_platform

    api_key = get_api_key(platform)
    if not api_key:
        return {"error": f"No API key configured for {platform}"}
    if is_manual_mode_key(api_key) or is_import_mode_key(api_key):
        return {"error": f"{platform} is in manual/import mode (no API access)"}

    try:
        platform_cls = get_platform(platform)
        platform_obj = platform_cls(api_key)
        articles = platform_obj.list_articles(limit)
        return {"platform": platform, "articles": articles, "count": len(articles)}
    except Exception as e:
        return {"error": f"Failed to query {platform}: {e}"}


@mcp.tool()
def crier_doctor() -> dict:
    """Validate all configured platform API keys.

    Tests each configured platform by making a lightweight API call.

    Examples:
        crier_doctor()
    """
    from .platforms import PLATFORMS, get_platform
    from .config import get_api_key, is_manual_mode_key, is_import_mode_key

    results = {}
    for name in sorted(PLATFORMS.keys()):
        api_key = get_api_key(name)
        if not api_key:
            results[name] = {"status": "not_configured"}
            continue
        if is_manual_mode_key(api_key):
            results[name] = {"status": "manual_mode"}
            continue
        if is_import_mode_key(api_key):
            results[name] = {"status": "import_mode"}
            continue

        try:
            platform_cls = get_platform(name)
            platform_obj = platform_cls(api_key)
            platform_obj.list_articles(limit=1)
            results[name] = {"status": "healthy"}
        except Exception as e:
            results[name] = {"status": "error", "error": str(e)}

    configured = sum(1 for v in results.values() if v["status"] != "not_configured")
    healthy = sum(1 for v in results.values() if v["status"] == "healthy")

    return {
        "platforms": results,
        "configured": configured,
        "healthy": healthy,
        "total": len(PLATFORMS),
    }


@mcp.tool()
def crier_stats(key: str, platform: str | None = None) -> dict:
    """Get cached engagement stats for an article.

    The key can be a slug or canonical URL. If platform is specified,
    returns stats for that platform only.

    Examples:
        crier_stats("code-without-purpose")
        crier_stats("code-without-purpose", platform="devto")
    """
    if platform:
        err = _validate_platform(platform)
        if err:
            return {"error": err}

    from .registry import get_cached_stats, get_article

    article = get_article(key)
    if not article:
        return {"error": f"Article not found: {key}"}

    slug = article["slug"]

    if platform:
        stats = get_cached_stats(slug, platform)
        return {"title": article["title"], "platform": platform, "stats": stats}

    result = {}
    for plat in article.get("platforms", {}):
        stats = get_cached_stats(slug, plat)
        if stats:
            result[plat] = stats

    return {"title": article["title"], "stats": result}


@mcp.tool()
def crier_stats_refresh(
    key: str | None = None,
    platform: str | None = None,
) -> dict:
    """Fetch fresh engagement stats from platform APIs.

    If key is provided, refreshes stats for that article.
    If platform is provided, only refreshes that platform's stats.

    Examples:
        crier_stats_refresh("code-without-purpose")
        crier_stats_refresh("code-without-purpose", platform="devto")
    """
    if platform:
        err = _validate_platform(platform)
        if err:
            return {"error": err}

    from .registry import get_article, get_all_articles, save_stats
    from .config import get_api_key, is_manual_mode_key, is_import_mode_key
    from .platforms import get_platform

    if key:
        article = get_article(key)
        if not article:
            return {"error": f"Article not found: {key}"}
        articles_to_refresh = {article["slug"]: article}
    else:
        articles_to_refresh = {}
        for k, v in get_all_articles().items():
            articles_to_refresh[v["slug"]] = v

    refreshed = []
    for slug, article in articles_to_refresh.items():
        canonical = article.get("canonical_url") or slug
        for plat, pdata in article.get("platforms", {}).items():
            if platform and plat != platform:
                continue
            if "deleted_at" in pdata:
                continue

            api_key = get_api_key(plat)
            if not api_key or is_manual_mode_key(api_key) or is_import_mode_key(api_key):
                continue

            pub_id = pdata.get("id")
            if not pub_id:
                continue

            try:
                platform_cls = get_platform(plat)
                platform_obj = platform_cls(api_key)
                if not platform_obj.supports_stats:
                    continue
                stats_result = platform_obj.get_stats(pub_id)
                if stats_result:
                    save_stats(
                        canonical, plat,
                        views=stats_result.views,
                        likes=stats_result.likes,
                        comments=stats_result.comments,
                        reposts=stats_result.reposts,
                    )
                    refreshed.append({
                        "title": article["title"],
                        "platform": plat,
                        "views": stats_result.views,
                        "likes": stats_result.likes,
                        "comments": stats_result.comments,
                        "reposts": stats_result.reposts,
                    })
            except Exception:
                continue

    return {"refreshed": refreshed, "count": len(refreshed)}


# ============================================================================
# Resources
# ============================================================================


@mcp.resource("crier://schema")
def get_schema() -> str:
    """Database schema for the crier registry."""
    from .registry import SCHEMA_SQL
    return SCHEMA_SQL


@mcp.resource("crier://config")
def get_config_resource() -> str:
    """Current crier configuration (API keys masked)."""
    from .config import (
        get_site_root, get_site_base_url, get_content_paths,
        get_exclude_patterns, get_file_extensions, get_default_profile,
        get_all_profiles, get_db_path,
    )
    config = {
        "site_root": str(get_site_root()) if get_site_root() else None,
        "site_base_url": get_site_base_url(),
        "content_paths": get_content_paths(),
        "exclude_patterns": get_exclude_patterns(),
        "file_extensions": get_file_extensions(),
        "default_profile": get_default_profile(),
        "profiles": get_all_profiles(),
        "db_path": str(get_db_path()),
    }
    return json.dumps(config, indent=2)


@mcp.resource("crier://platforms")
def get_platforms_resource() -> str:
    """All available platforms with their capabilities."""
    from .platforms import PLATFORMS
    from .config import get_api_key, get_platform_mode

    result = {}
    for name, cls in sorted(PLATFORMS.items()):
        result[name] = {
            "description": cls.description,
            "mode": get_platform_mode(name),
            "max_content_length": cls.max_content_length,
            "is_short_form": getattr(cls, "is_short_form", False),
            "supports_delete": cls.supports_delete,
            "supports_stats": cls.supports_stats,
            "supports_threads": cls.supports_threads,
            "configured": bool(get_api_key(name)),
        }
    return json.dumps(result, indent=2)


# ============================================================================
# Entry point
# ============================================================================


def main():
    """Run the MCP server."""
    import sys

    if "--http" in sys.argv:
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
