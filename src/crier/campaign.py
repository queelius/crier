"""Manifest-driven bulk publishing campaigns.

A campaign is a reviewable YAML manifest of (post x platform) cells to publish.
`plan_campaign` generates the manifest from a content scan plus the registry
(only cells not already published). Short-form platform cells carry an empty
`rewrite` field for an agent or human to fill in before running.
`run_campaign` executes each pending cell through `publish_one`, records the
result, and writes status back into the manifest, so a crashed or partial run
resumes by skipping cells already marked published.

The manifest lives at `<site_root>/.crier/campaigns/<name>.yaml`. Cells are
keyed by canonical_url (stable). Dry-run by default; apply=True publishes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config import (
    get_api_key,
    get_platform_mode,
    get_site_root,
    is_short_form_platform,
)
from .converters import parse_markdown_file
from .platforms import PLATFORMS
from .registry import is_published, record_failure, record_publication
from .utils import find_content_files


# --- manifest location and IO ----------------------------------------------


def campaigns_dir() -> Path:
    """Directory holding campaign manifests: <site_root>/.crier/campaigns."""
    root = get_site_root() or Path.cwd()
    return root / ".crier" / "campaigns"


def campaign_path(name: str) -> Path:
    return campaigns_dir() / f"{name}.yaml"


def save_manifest(name: str, manifest: dict) -> Path:
    path = campaign_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return path


def load_manifest(name: str) -> dict | None:
    path = campaign_path(name)
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# --- planning ---------------------------------------------------------------


def _default_api_platforms() -> list[str]:
    return [
        name
        for name in sorted(PLATFORMS)
        if get_api_key(name) and get_platform_mode(name) == "api"
    ]


def build_plan(name: str, files: list, platforms: list[str]) -> dict:
    """Build a manifest dict: one targets cell per (post, missing-platform).

    A post is included only if it has a canonical_url and at least one platform
    it is not already published to. Short-form platform cells get an empty
    `rewrite` field; long-form cells do not.
    """
    posts = []
    for f in files:
        try:
            article = parse_markdown_file(str(f))
        except Exception:
            continue
        if not article.canonical_url:
            continue
        targets: dict[str, dict] = {}
        for platform in platforms:
            if is_published(article.canonical_url, platform):
                continue
            cell: dict = {"status": "pending"}
            if is_short_form_platform(platform):
                cell["rewrite"] = ""
            targets[platform] = cell
        if targets:
            posts.append(
                {
                    "canonical_url": article.canonical_url,
                    "file": str(f),
                    "title": article.title,
                    "targets": targets,
                }
            )
    return {
        "campaign": name,
        "created": datetime.now(timezone.utc).isoformat(),
        "platforms": list(platforms),
        "posts": posts,
    }


def plan_campaign(
    name: str,
    *,
    path: str | None = None,
    platforms: list[str] | None = None,
    write: bool = True,
) -> dict:
    """Generate (and by default write) a campaign manifest."""
    files = find_content_files(path)
    platforms = platforms or _default_api_platforms()
    manifest = build_plan(name, files, platforms)
    if write:
        save_manifest(name, manifest)
    return manifest


# --- running ----------------------------------------------------------------


@dataclass
class CampaignRunSummary:
    """Outcome counts for a campaign run."""

    name: str
    published: int = 0
    failed: int = 0
    skipped: int = 0          # already published (resume)
    needs_rewrite: int = 0    # short-form cell with empty rewrite
    pending: int = 0          # dry-run: cells that would publish
    applied: bool = False
    error: str | None = None


def run_campaign(name: str, *, apply: bool = False) -> CampaignRunSummary:
    """Execute (or preview) a campaign's pending cells.

    Resumable and idempotent: cells already marked `published` are skipped.
    Short-form cells with an empty `rewrite` become `needs_rewrite` and are not
    published. Dry-run (apply=False) makes no publishes and no manifest writes.
    Recording is done here (publish_one does not touch the registry).
    """
    manifest = load_manifest(name)
    if manifest is None:
        return CampaignRunSummary(name=name, error=f"Campaign not found: {name}")

    from .publishing import publish_one

    summary = CampaignRunSummary(name=name, applied=apply)

    for post in manifest.get("posts", []):
        canonical = post.get("canonical_url")
        file = post.get("file")
        title = post.get("title")
        for platform, cell in post.get("targets", {}).items():
            if cell.get("status") == "published":
                summary.skipped += 1
                continue

            # Resume/idempotency against the REGISTRY, not just the manifest.
            # record_publication runs per-cell during a run, so the registry is
            # the live source of truth: a cell already published (by a prior
            # interrupted run, by an out-of-band publish, or by another tool)
            # is skipped here even if the manifest still says pending. This is
            # what makes a run crash-resumable and duplicate-safe.
            if canonical and is_published(canonical, platform):
                summary.skipped += 1
                if apply:
                    cell["status"] = "published"
                continue

            rewrite = cell.get("rewrite")
            if is_short_form_platform(platform) and not rewrite:
                cell["status"] = "needs_rewrite"
                summary.needs_rewrite += 1
                continue

            if not apply:
                summary.pending += 1
                continue

            outcome = publish_one(file, platform, rewrite_content=rewrite or None)
            result = outcome.result
            if result.success:
                if canonical:
                    record_publication(
                        canonical_url=canonical,
                        platform=platform,
                        article_id=result.article_id,
                        url=result.url,
                        title=title,
                        source_file=file,
                        rewritten=outcome.rewritten,
                        posted_content=outcome.posted_content,
                    )
                cell["status"] = "published"
                cell["url"] = result.url
                cell.pop("error", None)
                summary.published += 1
            else:
                if canonical:
                    record_failure(
                        canonical, platform, result.error or "unknown error",
                        title, file,
                    )
                cell["status"] = "failed"
                cell["error"] = result.error
                summary.failed += 1

    if apply:
        save_manifest(name, manifest)

    return summary
