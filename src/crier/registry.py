"""Publication registry backed by SQLite.

Registry v3: SQLite database at ~/.config/crier/crier.db (global).
Primary key is a slugified title. canonical_url is optional metadata.
No content hashes — change detection is dropped.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from slugify import slugify


CURRENT_VERSION = 3

# Module-level connection cache
_connection: sqlite3.Connection | None = None
_connection_path: str | None = None


SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS articles (
    slug TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    canonical_url TEXT,
    source_file TEXT,
    section TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_canonical_url
    ON articles(canonical_url) WHERE canonical_url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_source_file ON articles(source_file);

CREATE TABLE IF NOT EXISTS publications (
    slug TEXT NOT NULL REFERENCES articles(slug) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    platform_id TEXT,
    url TEXT,
    published_at TEXT NOT NULL,
    deleted_at TEXT,
    rewritten INTEGER NOT NULL DEFAULT 0,
    rewrite_author TEXT,
    posted_content TEXT,
    is_thread INTEGER NOT NULL DEFAULT 0,
    thread_ids TEXT,
    thread_urls TEXT,
    last_error TEXT,
    last_error_at TEXT,
    PRIMARY KEY (slug, platform)
);

CREATE TABLE IF NOT EXISTS stats (
    slug TEXT NOT NULL,
    platform TEXT NOT NULL,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    reposts INTEGER,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (slug, platform),
    FOREIGN KEY (slug, platform) REFERENCES publications(slug, platform) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
"""


def _get_db_path() -> Path:
    """Get database path from config."""
    from .config import get_db_path
    return get_db_path()


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Get or create a SQLite connection.

    Uses module-level cache for the default path. Pass explicit db_path
    for testing or alternate databases.
    """
    global _connection, _connection_path

    if db_path is not None:
        # Explicit path — don't cache (used by tests and migration)
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    path = _get_db_path()
    current_path = str(path)

    # Invalidate cache if path changed (e.g., CRIER_DB env var changed between tests)
    if _connection is not None and _connection_path != current_path:
        try:
            _connection.close()
        except Exception:
            pass
        _connection = None

    if _connection is not None:
        try:
            _connection.execute("SELECT 1")
            return _connection
        except sqlite3.ProgrammingError:
            _connection = None

    path.parent.mkdir(parents=True, exist_ok=True)
    _connection = sqlite3.connect(current_path)
    _connection.execute("PRAGMA journal_mode=WAL")
    _connection.execute("PRAGMA foreign_keys=ON")
    _connection.row_factory = sqlite3.Row
    _connection_path = current_path
    _init_db(_connection)
    return _connection


def reset_connection() -> None:
    """Close and reset the cached connection (for testing)."""
    global _connection, _connection_path
    if _connection is not None:
        try:
            _connection.close()
        except Exception:
            pass
        _connection = None
    _connection_path = None


def _init_db(conn: sqlite3.Connection) -> None:
    """Initialize database schema if needed."""
    conn.executescript(SCHEMA_SQL)
    # Check version
    row = conn.execute(
        "SELECT version FROM schema_version LIMIT 1"
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (CURRENT_VERSION,),
        )
        conn.commit()


def init_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Initialize a database (create tables). Returns the connection."""
    conn = get_connection(db_path)
    _init_db(conn)
    return conn


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

def make_slug(title: str) -> str:
    """Generate a URL-safe slug from a title."""
    return slugify(title, max_length=80)


def _ensure_unique_slug(conn: sqlite3.Connection, slug: str) -> str:
    """If slug already exists, append -2, -3, ... until unique."""
    if not conn.execute(
        "SELECT 1 FROM articles WHERE slug = ?", (slug,)
    ).fetchone():
        return slug
    base = slug
    counter = 2
    while conn.execute(
        "SELECT 1 FROM articles WHERE slug = ?", (slug,)
    ).fetchone():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def get_or_create_slug(
    title: str,
    canonical_url: str | None = None,
    source_file: str | Path | None = None,
    conn: sqlite3.Connection | None = None,
) -> str:
    """Find an existing slug or create a new article entry.

    Lookup order: canonical_url match → source_file match → title slug match.
    If no match, creates a new article with a unique slug.
    """
    if conn is None:
        conn = get_connection()

    # Try canonical_url lookup first
    if canonical_url:
        row = conn.execute(
            "SELECT slug FROM articles WHERE canonical_url = ?",
            (canonical_url,),
        ).fetchone()
        if row:
            return row["slug"]

    # Try source_file lookup
    if source_file:
        sf = str(source_file)
        row = conn.execute(
            "SELECT slug FROM articles WHERE source_file = ?", (sf,)
        ).fetchone()
        if row:
            return row["slug"]

    # Try exact slug match
    slug = make_slug(title)
    row = conn.execute(
        "SELECT slug FROM articles WHERE slug = ?", (slug,)
    ).fetchone()
    if row:
        return row["slug"]

    # Create new article
    slug = _ensure_unique_slug(conn, slug)
    section = infer_section(source_file)
    conn.execute(
        "INSERT INTO articles (slug, title, canonical_url, source_file, section) "
        "VALUES (?, ?, ?, ?, ?)",
        (slug, title, canonical_url, str(source_file) if source_file else None, section),
    )
    conn.commit()
    return slug


def find_slug(
    *,
    canonical_url: str | None = None,
    source_file: str | None = None,
    title: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> str | None:
    """Find a slug by canonical_url, source_file, or title. Returns None if not found."""
    if conn is None:
        conn = get_connection()

    if canonical_url:
        row = conn.execute(
            "SELECT slug FROM articles WHERE canonical_url = ?",
            (canonical_url,),
        ).fetchone()
        if row:
            return row["slug"]

    if source_file:
        row = conn.execute(
            "SELECT slug FROM articles WHERE source_file = ?",
            (str(source_file),),
        ).fetchone()
        if row:
            return row["slug"]

    if title:
        slug = make_slug(title)
        row = conn.execute(
            "SELECT slug FROM articles WHERE slug = ?", (slug,)
        ).fetchone()
        if row:
            return row["slug"]

    return None


# ---------------------------------------------------------------------------
# Section inference (kept from v2)
# ---------------------------------------------------------------------------

def infer_section(source_file: str | Path | None) -> str | None:
    """Infer content section from source file path.

    Extracts the first directory component after 'content/' if present,
    or the first directory component otherwise.

    Examples:
        "content/post/2026-01-slug/index.md" -> "post"
        "content/papers/my-paper/index.md" -> "papers"
        "posts/my-post.md" -> "posts"
        "index.md" -> None
        None -> None
    """
    if source_file is None:
        return None

    parts = Path(source_file).parts

    try:
        content_idx = list(parts).index("content")
        if content_idx + 1 < len(parts) - 1:
            return parts[content_idx + 1]
    except ValueError:
        pass

    if len(parts) > 1:
        return parts[0]

    return None


# ---------------------------------------------------------------------------
# Publication recording
# ---------------------------------------------------------------------------

def _update_article_metadata(
    conn: sqlite3.Connection,
    slug: str,
    *,
    title: str | None = None,
    source_file: str | Path | None = None,
    canonical_url: str | None = None,
    section: str | None = None,
) -> None:
    """Update article metadata fields that are non-null."""
    updates = []
    params: list = []
    if title:
        updates.append("title = ?")
        params.append(title)
    if source_file:
        updates.append("source_file = ?")
        params.append(str(source_file))
    if canonical_url:
        updates.append("canonical_url = ?")
        params.append(canonical_url)
    if section:
        updates.append("section = ?")
        params.append(section)
    if updates:
        params.append(slug)
        conn.execute(
            f"UPDATE articles SET {', '.join(updates)} WHERE slug = ?",
            params,
        )


def record_publication(
    canonical_url: str,
    platform: str,
    article_id: str | None,
    url: str | None,
    title: str | None = None,
    source_file: str | Path | None = None,
    rewritten: bool = False,
    rewrite_author: str | None = None,
    posted_content: str | None = None,
) -> None:
    """Record a successful publication to the registry."""
    conn = get_connection()

    slug = get_or_create_slug(
        title=title or "untitled",
        canonical_url=canonical_url,
        source_file=source_file,
        conn=conn,
    )

    _update_article_metadata(
        conn, slug,
        title=title, source_file=source_file, canonical_url=canonical_url,
    )

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO publications "
        "(slug, platform, platform_id, url, published_at, "
        "rewritten, rewrite_author, posted_content) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (slug, platform, article_id, url, now,
         1 if rewritten else 0, rewrite_author, posted_content),
    )
    conn.commit()


def record_thread_publication(
    canonical_url: str,
    platform: str,
    root_id: str | None,
    root_url: str | None,
    thread_ids: list[str],
    thread_urls: list[str] | None = None,
    title: str | None = None,
    source_file: str | Path | None = None,
    rewritten: bool = False,
    rewrite_author: str | None = None,
) -> None:
    """Record a thread publication to the registry."""
    conn = get_connection()

    slug = get_or_create_slug(
        title=title or "untitled",
        canonical_url=canonical_url,
        source_file=source_file,
        conn=conn,
    )

    _update_article_metadata(
        conn, slug,
        title=title, source_file=source_file, canonical_url=canonical_url,
    )

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO publications "
        "(slug, platform, platform_id, url, published_at, "
        "is_thread, thread_ids, thread_urls, rewritten, rewrite_author) "
        "VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
        (slug, platform, root_id, root_url, now,
         json.dumps(thread_ids), json.dumps(thread_urls) if thread_urls else None,
         1 if rewritten else 0, rewrite_author),
    )
    conn.commit()


def record_failure(
    canonical_url: str,
    platform: str,
    error_msg: str,
    title: str | None = None,
    source_file: str | Path | None = None,
) -> None:
    """Record a failed publication attempt."""
    conn = get_connection()

    slug = get_or_create_slug(
        title=title or "untitled",
        canonical_url=canonical_url,
        source_file=source_file,
        conn=conn,
    )

    now = datetime.now(timezone.utc).isoformat()

    # Check if publication exists (successful prior publish)
    existing = conn.execute(
        "SELECT 1 FROM publications WHERE slug = ? AND platform = ?",
        (slug, platform),
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE publications SET last_error = ?, last_error_at = ? "
            "WHERE slug = ? AND platform = ?",
            (error_msg, now, slug, platform),
        )
    else:
        conn.execute(
            "INSERT INTO publications (slug, platform, published_at, last_error, last_error_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (slug, platform, now, error_msg, now),
        )
    conn.commit()


def get_failures() -> list[dict[str, Any]]:
    """Get all publications with recorded failures."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT a.slug, a.title, a.source_file, a.canonical_url, "
        "p.platform, p.last_error, p.last_error_at "
        "FROM publications p JOIN articles a ON p.slug = a.slug "
        "WHERE p.last_error IS NOT NULL"
    ).fetchall()

    return [
        {
            "canonical_url": r["canonical_url"] or r["slug"],
            "platform": r["platform"],
            "error": r["last_error"],
            "error_at": r["last_error_at"],
            "title": r["title"],
            "source_file": r["source_file"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Lookups (backward-compat: accept canonical_url, look up internally)
# ---------------------------------------------------------------------------

def get_article(canonical_url: str) -> dict[str, Any] | None:
    """Get an article by slug or canonical URL."""
    conn = get_connection()
    slug = _resolve_slug(conn, canonical_url)
    if not slug:
        return None
    row = conn.execute("SELECT * FROM articles WHERE slug = ?", (slug,)).fetchone()
    if not row:
        return None
    return _article_row_to_dict(conn, row)


def get_article_by_slug(slug: str) -> dict[str, Any] | None:
    """Get an article by slug (native API)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM articles WHERE slug = ?", (slug,)
    ).fetchone()
    if not row:
        return None
    return _article_row_to_dict(conn, row)


def get_article_by_file(file_path: str | Path) -> tuple[str, dict[str, Any]] | None:
    """Find an article by its source file path.

    Returns (canonical_url, article_data) or None if not found.
    Backward compat: returns canonical_url as the key.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM articles WHERE source_file = ?",
        (str(file_path),),
    ).fetchone()
    if not row:
        return None

    key = row["canonical_url"] or row["slug"]
    return (key, _article_row_to_dict(conn, row))


def _article_row_to_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    """Convert an article row + its publications to the old dict format."""
    slug = row["slug"]

    # Get publications
    pubs = conn.execute(
        "SELECT * FROM publications WHERE slug = ?", (slug,)
    ).fetchall()

    platforms = {}
    for p in pubs:
        pdata: dict[str, Any] = {
            "id": p["platform_id"],
            "url": p["url"],
            "published_at": p["published_at"],
            "updated_at": p["published_at"],  # backward compat
        }
        if p["deleted_at"]:
            pdata["deleted_at"] = p["deleted_at"]
        if p["rewritten"]:
            pdata["rewritten"] = True
            if p["rewrite_author"]:
                pdata["rewrite_author"] = p["rewrite_author"]
            if p["posted_content"]:
                pdata["posted_content"] = p["posted_content"]
        if p["is_thread"]:
            pdata["is_thread"] = True
            if p["thread_ids"]:
                pdata["thread_ids"] = json.loads(p["thread_ids"])
            if p["thread_urls"]:
                pdata["thread_urls"] = json.loads(p["thread_urls"])
        if p["last_error"]:
            pdata["last_error"] = p["last_error"]
            pdata["last_error_at"] = p["last_error_at"]
        platforms[p["platform"]] = pdata

    result: dict[str, Any] = {
        "slug": row["slug"],
        "title": row["title"],
        "source_file": row["source_file"],
        "canonical_url": row["canonical_url"],
        "platforms": platforms,
    }
    if row["section"]:
        result["section"] = row["section"]
    if row["archived_at"]:
        result["archived"] = True
        result["archived_at"] = row["archived_at"]
    return result


def get_all_articles() -> dict[str, Any]:
    """Get all tracked articles. Returns dict keyed by canonical_url (or slug)."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM articles").fetchall()
    result = {}
    for row in rows:
        key = row["canonical_url"] or row["slug"]
        result[key] = _article_row_to_dict(conn, row)
    return result


def get_platform_publications(platform: str) -> list[dict[str, Any]]:
    """Get all publications for a specific platform."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT a.*, p.platform_id, p.url AS platform_url, "
        "p.published_at, p.rewritten, p.rewrite_author "
        "FROM articles a JOIN publications p ON a.slug = p.slug "
        "WHERE p.platform = ? AND p.deleted_at IS NULL",
        (platform,),
    ).fetchall()

    return [
        {
            "canonical_url": r["canonical_url"] or r["slug"],
            "title": r["title"],
            "source_file": r["source_file"],
            "platform_id": r["platform_id"],
            "platform_url": r["platform_url"],
            "published_at": r["published_at"],
            "rewritten": bool(r["rewritten"]),
            "rewrite_author": r["rewrite_author"],
        }
        for r in rows
    ]


def _resolve_slug(conn: sqlite3.Connection, key: str) -> str | None:
    """Resolve a key (slug or canonical_url) to a slug."""
    # Try as slug first (cheaper — primary key lookup)
    row = conn.execute("SELECT slug FROM articles WHERE slug = ?", (key,)).fetchone()
    if row:
        return row["slug"]
    # Try as canonical_url
    row = conn.execute(
        "SELECT slug FROM articles WHERE canonical_url = ?", (key,)
    ).fetchone()
    return row["slug"] if row else None


def is_published(canonical_url: str, platform: str) -> bool:
    """Check if an article has been published to a specific platform.

    Accepts either a slug or canonical_url as the first argument.
    """
    conn = get_connection()
    slug = _resolve_slug(conn, canonical_url)
    if not slug:
        return False
    row = conn.execute(
        "SELECT 1 FROM publications "
        "WHERE slug = ? AND platform = ? "
        "AND deleted_at IS NULL AND platform_id IS NOT NULL",
        (slug, platform),
    ).fetchone()
    return row is not None


def get_publication_id(canonical_url: str, platform: str) -> str | None:
    """Get the platform-specific article ID.

    Accepts either a slug or canonical_url as the first argument.
    """
    conn = get_connection()
    slug = _resolve_slug(conn, canonical_url)
    if not slug:
        return None
    row = conn.execute(
        "SELECT platform_id FROM publications WHERE slug = ? AND platform = ?",
        (slug, platform),
    ).fetchone()
    return row["platform_id"] if row else None


def get_publication_info(
    canonical_url: str, platform: str
) -> dict[str, Any] | None:
    """Get full publication info for a platform.

    Accepts either a slug or canonical_url as the first argument.
    """
    conn = get_connection()
    slug = _resolve_slug(conn, canonical_url)
    if not slug:
        return None
    row = conn.execute(
        "SELECT * FROM publications WHERE slug = ? AND platform = ?",
        (slug, platform),
    ).fetchone()
    if not row:
        return None
    return {
        "article_id": row["platform_id"],
        "url": row["url"],
        "published_at": row["published_at"],
        "updated_at": row["published_at"],
        "rewritten": bool(row["rewritten"]),
        "rewrite_author": row["rewrite_author"],
    }




# ---------------------------------------------------------------------------
# Deletion, archiving
# ---------------------------------------------------------------------------

def record_deletion(canonical_url: str, platform: str) -> bool:
    """Record that a publication was deleted from a platform.

    Accepts either a slug or canonical_url as the first argument.
    """
    conn = get_connection()
    slug = _resolve_slug(conn, canonical_url)
    if not slug:
        return False
    now = datetime.now(timezone.utc).isoformat()
    result = conn.execute(
        "UPDATE publications SET deleted_at = ? "
        "WHERE slug = ? AND platform = ?",
        (now, slug, platform),
    )
    conn.commit()
    return result.rowcount > 0


def is_deleted(canonical_url: str, platform: str) -> bool:
    """Check if a publication has been deleted from a platform.

    Accepts either a slug or canonical_url as the first argument.
    """
    conn = get_connection()
    slug = _resolve_slug(conn, canonical_url)
    if not slug:
        return False
    row = conn.execute(
        "SELECT deleted_at FROM publications WHERE slug = ? AND platform = ?",
        (slug, platform),
    ).fetchone()
    return row is not None and row["deleted_at"] is not None


def remove_article(canonical_url: str) -> bool:
    """Remove an article from the registry.

    Accepts either a slug or canonical_url as the first argument.
    """
    conn = get_connection()
    slug = _resolve_slug(conn, canonical_url)
    if not slug:
        return False
    result = conn.execute("DELETE FROM articles WHERE slug = ?", (slug,))
    conn.commit()
    return result.rowcount > 0


def remove_publication(canonical_url: str, platform: str) -> bool:
    """Remove a single platform publication from the registry.

    Accepts either a slug or canonical_url as the first argument.
    """
    conn = get_connection()
    slug = _resolve_slug(conn, canonical_url)
    if not slug:
        return False
    result = conn.execute(
        "DELETE FROM publications WHERE slug = ? AND platform = ?",
        (slug, platform),
    )
    conn.commit()
    return result.rowcount > 0


def set_archived(canonical_url: str, archived: bool = True) -> bool:
    """Set the archived status of an article.

    Accepts either a slug or canonical_url as the first argument.
    """
    conn = get_connection()
    slug = _resolve_slug(conn, canonical_url)
    if not slug:
        return False
    now = datetime.now(timezone.utc).isoformat() if archived else None
    conn.execute("UPDATE articles SET archived_at = ? WHERE slug = ?", (now, slug))
    conn.commit()
    return True


def is_archived(canonical_url: str) -> bool:
    """Check if an article is archived.

    Accepts either a slug or canonical_url as the first argument.
    """
    conn = get_connection()
    slug = _resolve_slug(conn, canonical_url)
    if not slug:
        return False
    row = conn.execute(
        "SELECT archived_at FROM articles WHERE slug = ?", (slug,)
    ).fetchone()
    return row is not None and row["archived_at"] is not None


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def save_stats(
    canonical_url: str,
    platform: str,
    views: int | None = None,
    likes: int | None = None,
    comments: int | None = None,
    reposts: int | None = None,
) -> bool:
    """Save engagement stats for a publication.

    Accepts either a slug or canonical_url as the first argument.
    """
    conn = get_connection()
    slug = _resolve_slug(conn, canonical_url)
    if not slug:
        return False

    # Check publication exists (FK constraint)
    pub = conn.execute(
        "SELECT 1 FROM publications WHERE slug = ? AND platform = ?",
        (slug, platform),
    ).fetchone()
    if not pub:
        return False

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO stats (slug, platform, views, likes, comments, reposts, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (slug, platform, views, likes, comments, reposts, now),
    )
    conn.commit()
    return True


def get_cached_stats(canonical_url: str, platform: str) -> dict[str, Any] | None:
    """Get cached stats for a publication.

    Accepts either a slug or canonical_url as the first argument.
    """
    conn = get_connection()
    slug = _resolve_slug(conn, canonical_url)
    if not slug:
        return None

    row = conn.execute(
        "SELECT * FROM stats WHERE slug = ? AND platform = ?",
        (slug, platform),
    ).fetchone()
    if not row:
        return None
    return {
        "views": row["views"],
        "likes": row["likes"],
        "comments": row["comments"],
        "reposts": row["reposts"],
        "fetched_at": row["fetched_at"],
    }


def get_stats_age_seconds(canonical_url: str, platform: str) -> float | None:
    """Get the age of cached stats in seconds."""
    stats = get_cached_stats(canonical_url, platform)
    if not stats or "fetched_at" not in stats:
        return None
    fetched_at = datetime.fromisoformat(stats["fetched_at"])
    now = datetime.now(timezone.utc)
    return (now - fetched_at).total_seconds()


# ---------------------------------------------------------------------------
# Thread helpers
# ---------------------------------------------------------------------------

def is_thread(canonical_url: str, platform: str) -> bool:
    """Check if a publication is a thread.

    Accepts either a slug or canonical_url as the first argument.
    """
    conn = get_connection()
    slug = _resolve_slug(conn, canonical_url)
    if not slug:
        return False
    row = conn.execute(
        "SELECT is_thread FROM publications WHERE slug = ? AND platform = ?",
        (slug, platform),
    ).fetchone()
    return row is not None and bool(row["is_thread"])


def get_thread_ids(canonical_url: str, platform: str) -> list[str] | None:
    """Get the list of post IDs for a thread publication.

    Accepts either a slug or canonical_url as the first argument.
    """
    conn = get_connection()
    slug = _resolve_slug(conn, canonical_url)
    if not slug:
        return None
    row = conn.execute(
        "SELECT thread_ids FROM publications WHERE slug = ? AND platform = ?",
        (slug, platform),
    ).fetchone()
    if not row or not row["thread_ids"]:
        return None
    return json.loads(row["thread_ids"])


# ---------------------------------------------------------------------------
# Backward-compat: registry path and load/save
# ---------------------------------------------------------------------------

def get_registry_path() -> Path:
    """Get the path to the registry (now returns DB path)."""
    return _get_db_path()


def load_registry() -> dict[str, Any]:
    """Load all articles as a dict (backward compat for summary command)."""
    articles = get_all_articles()
    return {"version": CURRENT_VERSION, "articles": articles}


def save_registry(registry: dict[str, Any]) -> None:
    """No-op for backward compat. SQLite handles persistence."""
    pass


# ---------------------------------------------------------------------------
# Migration from YAML v2
# ---------------------------------------------------------------------------

def migrate_yaml_to_sqlite(yaml_path: Path, db_path: Path | None = None) -> dict[str, Any]:
    """Migrate a YAML registry (v2) to SQLite (v3).

    Returns migration stats: {"articles": N, "publications": N, "skipped": N}.
    """
    import yaml as yaml_lib

    if not yaml_path.exists():
        return {"articles": 0, "publications": 0, "skipped": 0}

    with open(yaml_path) as f:
        data = yaml_lib.safe_load(f) or {}

    articles_data = data.get("articles", {})
    if not articles_data:
        return {"articles": 0, "publications": 0, "skipped": 0}

    if db_path is None:
        db_path = _get_db_path()

    conn = get_connection(db_path)
    _init_db(conn)

    stats = {"articles": 0, "publications": 0, "skipped": 0}

    for canonical_url, article in articles_data.items():
        title = article.get("title")
        if not title:
            stats["skipped"] += 1
            continue

        slug = make_slug(title)
        slug = _ensure_unique_slug(conn, slug)

        conn.execute(
            "INSERT OR IGNORE INTO articles (slug, title, canonical_url, source_file, section) "
            "VALUES (?, ?, ?, ?, ?)",
            (slug, title, canonical_url,
             article.get("source_file"), article.get("section")),
        )
        stats["articles"] += 1

        # Handle archived
        if article.get("archived"):
            conn.execute(
                "UPDATE articles SET archived_at = ? WHERE slug = ?",
                (article.get("archived_at", datetime.now(timezone.utc).isoformat()), slug),
            )

        for platform_name, pdata in article.get("platforms", {}).items():
            # Skip entries that are error-only (no platform_id, no url)
            pub_at = pdata.get("published_at", datetime.now(timezone.utc).isoformat())

            conn.execute(
                "INSERT OR IGNORE INTO publications "
                "(slug, platform, platform_id, url, published_at, deleted_at, "
                "rewritten, rewrite_author, posted_content, "
                "is_thread, thread_ids, thread_urls, last_error, last_error_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    slug, platform_name,
                    pdata.get("id"),
                    pdata.get("url"),
                    pub_at,
                    pdata.get("deleted_at"),
                    1 if pdata.get("rewritten") else 0,
                    pdata.get("rewrite_author"),
                    pdata.get("posted_content"),
                    1 if pdata.get("is_thread") else 0,
                    json.dumps(pdata["thread_ids"]) if pdata.get("thread_ids") else None,
                    json.dumps(pdata["thread_urls"]) if pdata.get("thread_urls") else None,
                    pdata.get("last_error"),
                    pdata.get("last_error_at"),
                ),
            )

            # Migrate stats if present
            if "stats" in pdata:
                s = pdata["stats"]
                conn.execute(
                    "INSERT OR IGNORE INTO stats "
                    "(slug, platform, views, likes, comments, reposts, fetched_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (slug, platform_name,
                     s.get("views"), s.get("likes"), s.get("comments"),
                     s.get("reposts"), s.get("fetched_at", pub_at)),
                )

            stats["publications"] += 1

    conn.commit()

    # Rename old YAML file
    backup_path = yaml_path.with_suffix(".yaml.bak")
    yaml_path.rename(backup_path)

    return stats
