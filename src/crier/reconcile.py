"""Reconcile live platform state with the registry.

Cures the published-but-untracked drift: a post can exist live on a platform
but be missing from the registry (published out-of-band, or a
failed-then-actually-succeeded API call). reconcile diffs each API platform's
live post list against the registry and classifies into three buckets; with
apply=True it backfills untracked-live publications and soft-deletes ones that
are gone from the platform.

Scope: API-mode platforms only (manual/import have no live list). Title-drift
between the registry and the content file is a separate concern and is out of
scope here; this reconciles live-platform state against the registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import get_api_key, get_platform_mode
from .platforms import PLATFORMS, get_platform
from .registry import (
    get_platform_publications,
    make_slug,
    record_deletion,
    record_publication,
)


@dataclass
class ReconcileEntry:
    """One reconciled item in a platform's report."""

    platform: str
    bucket: str  # "in_both" | "untracked_live" | "gone_from_platform"
    title: str | None = None
    live_id: str | None = None
    live_url: str | None = None
    canonical_url: str | None = None


@dataclass
class ReconcileReport:
    """Per-platform reconcile result."""

    platform: str
    in_both: list[ReconcileEntry] = field(default_factory=list)
    untracked_live: list[ReconcileEntry] = field(default_factory=list)
    gone_from_platform: list[ReconcileEntry] = field(default_factory=list)
    applied: bool = False
    error: str | None = None


def match_live_to_registry(
    live_post: dict, registry_rows: list[dict]
) -> dict | None:
    """Return the registry row matching a live post, or None.

    Tried in order of decreasing reliability:
      1. platform_id equality (the strongest signal),
      2. platform_url equality,
      3. slug(title) equality (fuzzy fallback).

    Pure: no I/O, fully unit-testable.
    """
    lid = live_post.get("id")
    if lid is not None:
        lid_s = str(lid)
        for r in registry_rows:
            if r.get("platform_id") and str(r["platform_id"]) == lid_s:
                return r

    lurl = live_post.get("url")
    if lurl:
        for r in registry_rows:
            if r.get("platform_url") and r["platform_url"] == lurl:
                return r

    ltitle = live_post.get("title")
    if ltitle:
        lslug = make_slug(ltitle)
        for r in registry_rows:
            if r.get("title") and make_slug(r["title"]) == lslug:
                return r

    return None


def reconcile_platform(
    platform_name: str, *, apply: bool = False, limit: int = 100
) -> ReconcileReport:
    """Diff one API platform's live posts against the registry.

    Returns a ReconcileReport with three buckets. When apply=True, untracked
    live posts are backfilled via record_publication and registry rows gone
    from the platform are soft-deleted via record_deletion. Non-API platforms
    or missing keys produce a report with .error set and empty buckets.
    """
    mode = get_platform_mode(platform_name)
    if mode != "api":
        return ReconcileReport(
            platform=platform_name,
            error=f"{platform_name} is in {mode} mode (not API)",
        )

    api_key = get_api_key(platform_name)
    if not api_key:
        return ReconcileReport(
            platform=platform_name,
            error=f"No API key configured for {platform_name}",
        )

    try:
        live_posts = get_platform(platform_name)(api_key).list_articles(limit)
    except Exception as e:
        return ReconcileReport(
            platform=platform_name,
            error=f"Failed to list {platform_name}: {e}",
        )

    registry_rows = get_platform_publications(platform_name)

    # Safety guard: an empty live listing while the registry has publications is
    # almost always a broken/limited listing (auth quirk, pagination cap,
    # rate-limit), not a real mass-deletion. Marking everything "gone" here and
    # soft-deleting on --apply would wipe valid history. The list_articles
    # exception path covers a raised error; this covers an empty-but-200
    # response (e.g. the old bluesky limit>100 bug). Refuse rather than guess.
    if registry_rows and not live_posts:
        return ReconcileReport(
            platform=platform_name,
            error=(
                f"Live listing for {platform_name} returned 0 posts but the "
                f"registry has {len(registry_rows)} publication(s); refusing to "
                f"reconcile (would falsely mark all as gone). Check the "
                f"platform's listing/auth before retrying."
            ),
        )

    report = ReconcileReport(platform=platform_name, applied=apply)
    matched_canonicals: set[str] = set()

    for lp in live_posts:
        live_id = str(lp["id"]) if lp.get("id") is not None else None
        live_url = lp.get("url")
        title = lp.get("title")
        row = match_live_to_registry(lp, registry_rows)
        if row:
            matched_canonicals.add(row["canonical_url"])
            report.in_both.append(
                ReconcileEntry(
                    platform=platform_name, bucket="in_both", title=title,
                    live_id=live_id, live_url=live_url,
                    canonical_url=row["canonical_url"],
                )
            )
        else:
            report.untracked_live.append(
                ReconcileEntry(
                    platform=platform_name, bucket="untracked_live",
                    title=title, live_id=live_id, live_url=live_url,
                )
            )
            if apply:
                record_publication(
                    canonical_url=None,
                    platform=platform_name,
                    article_id=live_id,
                    url=live_url,
                    title=title,
                )

    for r in registry_rows:
        if r["canonical_url"] not in matched_canonicals:
            report.gone_from_platform.append(
                ReconcileEntry(
                    platform=platform_name, bucket="gone_from_platform",
                    title=r.get("title"), canonical_url=r.get("canonical_url"),
                    live_id=str(r["platform_id"]) if r.get("platform_id") else None,
                    live_url=r.get("platform_url"),
                )
            )
            if apply:
                record_deletion(r["canonical_url"], platform_name)

    return report


def reconcile(
    platforms: list[str] | None = None, *, apply: bool = False, limit: int = 100
) -> dict[str, ReconcileReport]:
    """Reconcile multiple platforms. Defaults to all configured API platforms."""
    if platforms is None:
        platforms = [
            name
            for name in sorted(PLATFORMS)
            if get_api_key(name) and get_platform_mode(name) == "api"
        ]
    return {p: reconcile_platform(p, apply=apply, limit=limit) for p in platforms}
