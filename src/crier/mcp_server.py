"""MCP Server for crier — cross-posting registry tools for Claude Code.

Exposes the crier SQLite registry as MCP tools so Claude Code can query
publications, find unposted content, and manage the registry.

Usage:
    crier mcp            # Start stdio server (for Claude Code)
    python -m crier.mcp  # Alternative entry point

Tools:
    - crier_query: Search articles by section, platform, or archived status
    - crier_missing: Find content not yet published to specified platforms
    - crier_article: Get full details for a specific article
    - crier_publications: Get all publications for a platform
    - crier_record: Record a manual publication
    - crier_stats: Get cached engagement stats
    - crier_sql: Execute SELECT queries on the registry DB
    - crier_summary: Get registry summary statistics
"""

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="crier",
    instructions=(
        "Crier is a cross-posting tool that tracks blog content published to "
        "multiple platforms (devto, hashnode, bluesky, mastodon, etc.). "
        "Use these tools to query what's been published, find content that "
        "needs posting, and manage the publication registry."
    ),
)


def _get_conn():
    """Get a connection to the registry DB."""
    from .registry import get_connection
    return get_connection()


# ============================================================================
# Tools
# ============================================================================


@mcp.tool()
def crier_query(
    section: str | None = None,
    platform: str | None = None,
    archived: bool | None = None,
    limit: int = 50,
) -> str:
    """Search articles in the registry.

    Filter by section (e.g., "post", "papers"), platform (e.g., "devto"),
    or archived status. Returns JSON array of matching articles.
    """
    conn = _get_conn()
    conditions = []
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
        # Count publications
        pub_count = conn.execute(
            "SELECT COUNT(*) as n FROM publications "
            "WHERE slug = ? AND deleted_at IS NULL AND platform_id IS NOT NULL",
            (r["slug"],),
        ).fetchone()["n"]

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
            "publication_count": pub_count,
        })

    return json.dumps(results, indent=2)


@mcp.tool()
def crier_missing(
    platforms: list[str],
    section: str | None = None,
    limit: int = 50,
) -> str:
    """Find articles NOT published to the specified platforms.

    Returns articles that exist in the registry but are missing
    from one or more of the listed platforms.
    """
    conn = _get_conn()
    conditions = ["a.archived_at IS NULL"]
    params: list[Any] = []

    if section:
        conditions.append("a.section = ?")
        params.append(section)

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""

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

    return json.dumps(results, indent=2)


@mcp.tool()
def crier_article(key: str) -> str:
    """Get full details for a specific article.

    The key can be a slug, canonical URL, or source file path.
    Returns JSON with article metadata and all publication records.
    """
    from .registry import get_article, get_article_by_file

    # Try as slug/canonical_url
    article = get_article(key)
    if not article:
        # Try as file path
        result = get_article_by_file(key)
        if result:
            _, article = result

    if not article:
        return json.dumps({"error": f"Article not found: {key}"})

    return json.dumps(article, indent=2, default=str)


@mcp.tool()
def crier_publications(platform: str) -> str:
    """Get all publications for a specific platform.

    Returns JSON array with article title, platform URL,
    published date, and rewrite status.
    """
    from .registry import get_platform_publications
    pubs = get_platform_publications(platform)
    return json.dumps(pubs, indent=2, default=str)


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
) -> str:
    """Record a publication to the registry.

    Creates the article if it doesn't exist, then records
    the publication for the specified platform.
    """
    from .registry import record_publication

    record_publication(
        canonical_url=canonical_url or "",
        platform=platform,
        article_id=platform_id,
        url=url,
        title=title,
        source_file=source_file,
        rewritten=rewritten,
        rewrite_author=rewrite_author,
        posted_content=posted_content,
    )

    return json.dumps({
        "success": True,
        "message": f"Recorded {title!r} → {platform}",
    })


@mcp.tool()
def crier_stats(key: str, platform: str | None = None) -> str:
    """Get cached engagement stats for an article.

    The key can be a slug or canonical URL. If platform is specified,
    returns stats for that platform only. Otherwise returns all platforms.
    """
    from .registry import get_cached_stats, get_article

    article = get_article(key)
    if not article:
        return json.dumps({"error": f"Article not found: {key}"})

    slug = article["slug"]

    if platform:
        stats = get_cached_stats(slug, platform)
        return json.dumps({"platform": platform, "stats": stats}, default=str)

    # All platforms
    result = {}
    for plat in article.get("platforms", {}):
        stats = get_cached_stats(slug, plat)
        if stats:
            result[plat] = stats

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def crier_sql(query: str) -> str:
    """Execute a SELECT query on the registry database.

    Only SELECT statements are allowed. Tables: articles, publications, stats.

    Example queries:
    - SELECT slug, title FROM articles ORDER BY created_at DESC LIMIT 10
    - SELECT a.title, p.platform, p.url FROM articles a JOIN publications p ON a.slug = p.slug
    - SELECT platform, COUNT(*) as n FROM publications GROUP BY platform
    """
    query_stripped = query.strip().upper()
    if not query_stripped.startswith("SELECT"):
        return json.dumps({"error": "Only SELECT queries are allowed"})

    conn = _get_conn()
    try:
        rows = conn.execute(query).fetchall()
        if not rows:
            return json.dumps({"rows": [], "count": 0})

        columns = rows[0].keys()
        result = [dict(zip(columns, row)) for row in rows]
        return json.dumps({"rows": result, "count": len(result)}, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def crier_summary() -> str:
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

    return json.dumps({
        "total_articles": total,
        "by_section": {r["s"]: r["n"] for r in sections},
        "by_platform": {r["platform"]: r["n"] for r in platforms},
        "unposted": unposted,
    }, indent=2)


# ============================================================================
# Resources
# ============================================================================


@mcp.resource("crier://schema")
def get_schema() -> str:
    """Database schema for the crier registry."""
    from .registry import SCHEMA_SQL
    return SCHEMA_SQL


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
