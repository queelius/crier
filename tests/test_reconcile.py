"""Tests for the reconcile engine (live platform state vs registry)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from crier.reconcile import (
    ReconcileReport,
    match_live_to_registry,
    reconcile_platform,
)


def _row(**kw):
    base = {
        "canonical_url": "https://x/p/",
        "title": "T",
        "platform_id": "1",
        "platform_url": "https://dev/1",
    }
    base.update(kw)
    return base


# --- pure matcher -----------------------------------------------------------


def test_match_by_platform_id():
    rows = [_row(platform_id="abc", canonical_url="https://x/a/")]
    live = {"id": "abc", "url": "https://dev/zzz", "title": "Different"}
    assert match_live_to_registry(live, rows)["canonical_url"] == "https://x/a/"


def test_match_by_url_when_id_differs():
    rows = [_row(platform_id="abc", platform_url="https://dev/9", canonical_url="https://x/b/")]
    live = {"id": "nomatch", "url": "https://dev/9", "title": "Z"}
    assert match_live_to_registry(live, rows)["canonical_url"] == "https://x/b/"


def test_match_by_slug_fallback():
    rows = [_row(platform_id="abc", platform_url="https://dev/1", title="My Post", canonical_url="https://x/c/")]
    live = {"id": "none", "url": "none-url", "title": "My Post"}
    assert match_live_to_registry(live, rows)["canonical_url"] == "https://x/c/"


def test_no_match_returns_none():
    rows = [_row()]
    assert match_live_to_registry({"id": "z", "url": "z2", "title": "Nope"}, rows) is None


def test_id_precedence_over_slug():
    rows = [
        _row(platform_id="ID1", title="Same Title", canonical_url="https://x/right/"),
        _row(platform_id="ID2", title="Same Title", canonical_url="https://x/wrong/"),
    ]
    live = {"id": "ID1", "url": "u", "title": "Same Title"}
    assert match_live_to_registry(live, rows)["canonical_url"] == "https://x/right/"


def test_match_handles_numeric_live_id():
    """Mastodon returns numeric ids; registry stores them as strings."""
    rows = [_row(platform_id="116522", canonical_url="https://x/m/")]
    live = {"id": 116522, "url": "u", "title": "Toot"}
    assert match_live_to_registry(live, rows)["canonical_url"] == "https://x/m/"


# --- engine -----------------------------------------------------------------


def _patch_engine(mode="api", api_key="real-key", live=None, registry=None):
    """Helper: returns a context-manager stack of the 4 read-side patches."""
    live = live or []
    registry = registry or []
    inst = MagicMock()
    inst.list_articles.return_value = live
    return (
        patch("crier.reconcile.get_platform_mode", return_value=mode),
        patch("crier.reconcile.get_api_key", return_value=api_key),
        patch("crier.reconcile.get_platform", return_value=lambda _k: inst),
        patch("crier.reconcile.get_platform_publications", return_value=registry),
    )


def test_reconcile_non_api_mode_errors():
    p_mode, p_key, p_plat, p_pubs = _patch_engine(mode="manual")
    with p_mode, p_key, p_plat, p_pubs:
        report = reconcile_platform("twitter")
    assert isinstance(report, ReconcileReport)
    assert report.error is not None
    assert "manual" in report.error
    assert report.untracked_live == []


def test_reconcile_missing_key_errors():
    p_mode, p_key, p_plat, p_pubs = _patch_engine(api_key=None)
    with p_mode, p_key, p_plat, p_pubs:
        report = reconcile_platform("devto")
    assert report.error is not None
    assert "No API key" in report.error


def test_reconcile_untracked_live():
    live = [{"id": "999", "url": "https://dev.to/x/999", "title": "Ghost Post"}]
    p_mode, p_key, p_plat, p_pubs = _patch_engine(live=live, registry=[])
    with p_mode, p_key, p_plat, p_pubs:
        report = reconcile_platform("devto")
    assert len(report.untracked_live) == 1
    assert report.untracked_live[0].live_id == "999"
    assert report.in_both == []
    assert report.gone_from_platform == []


def test_reconcile_in_both():
    live = [{"id": "1", "url": "https://dev/1", "title": "T"}]
    registry = [_row(platform_id="1", canonical_url="https://x/p/")]
    p_mode, p_key, p_plat, p_pubs = _patch_engine(live=live, registry=registry)
    with p_mode, p_key, p_plat, p_pubs:
        report = reconcile_platform("devto")
    assert len(report.in_both) == 1
    assert report.in_both[0].canonical_url == "https://x/p/"
    assert report.untracked_live == []
    assert report.gone_from_platform == []


def test_reconcile_gone_from_platform():
    # Live listing is non-empty (so the empty-guard does not trip), but one
    # registry row is not present in it -> gone.
    live = [{"id": "present", "url": "https://dev/present", "title": "Present"}]
    registry = [
        _row(platform_id="present", canonical_url="https://x/ok/"),
        _row(platform_id="42", canonical_url="https://x/gone/"),
    ]
    p_mode, p_key, p_plat, p_pubs = _patch_engine(live=live, registry=registry)
    with p_mode, p_key, p_plat, p_pubs:
        report = reconcile_platform("devto")
    assert len(report.in_both) == 1
    assert len(report.gone_from_platform) == 1
    assert report.gone_from_platform[0].canonical_url == "https://x/gone/"


def test_reconcile_empty_listing_guard_refuses():
    """An empty live listing while the registry has rows must NOT mark gone.

    Guards against the bluesky-returns-0 class of bug wiping valid history.
    """
    registry = [_row(platform_id="42", canonical_url="https://x/keep/")]
    p_mode, p_key, p_plat, p_pubs = _patch_engine(live=[], registry=registry)
    with p_mode, p_key, p_plat, p_pubs, \
            patch("crier.reconcile.record_deletion") as rec_del:
        report = reconcile_platform("devto", apply=True)
    assert report.error is not None
    assert "0 posts" in report.error
    assert report.gone_from_platform == []
    rec_del.assert_not_called()


def test_reconcile_empty_listing_empty_registry_is_fine():
    """Empty live + empty registry is not an error (nothing to do)."""
    p_mode, p_key, p_plat, p_pubs = _patch_engine(live=[], registry=[])
    with p_mode, p_key, p_plat, p_pubs:
        report = reconcile_platform("devto")
    assert report.error is None
    assert report.in_both == [] and report.gone_from_platform == []


def test_reconcile_dry_run_makes_no_writes():
    live = [{"id": "999", "url": "u", "title": "Ghost"}]
    registry = [_row(platform_id="42", canonical_url="https://x/gone/")]
    p_mode, p_key, p_plat, p_pubs = _patch_engine(live=live, registry=registry)
    with p_mode, p_key, p_plat, p_pubs, \
            patch("crier.reconcile.record_publication") as rec_pub, \
            patch("crier.reconcile.record_deletion") as rec_del:
        report = reconcile_platform("devto", apply=False)
    rec_pub.assert_not_called()
    rec_del.assert_not_called()
    assert report.applied is False
    assert len(report.untracked_live) == 1
    assert len(report.gone_from_platform) == 1


def test_reconcile_apply_backfills_and_deletes():
    live = [{"id": "999", "url": "https://dev/999", "title": "Ghost"}]
    registry = [_row(platform_id="42", canonical_url="https://x/gone/")]
    p_mode, p_key, p_plat, p_pubs = _patch_engine(live=live, registry=registry)
    with p_mode, p_key, p_plat, p_pubs, \
            patch("crier.reconcile.record_publication") as rec_pub, \
            patch("crier.reconcile.record_deletion") as rec_del:
        report = reconcile_platform("devto", apply=True)
    rec_pub.assert_called_once()
    # backfill uses canonical_url=None and the live id/url/title
    _, kwargs = rec_pub.call_args
    assert kwargs["platform"] == "devto"
    assert kwargs["article_id"] == "999"
    assert kwargs["canonical_url"] is None
    rec_del.assert_called_once_with("https://x/gone/", "devto")
    assert report.applied is True


def test_reconcile_default_selects_api_platforms_only(monkeypatch):
    """reconcile(None) reconciles only configured API-mode platforms."""
    import crier.reconcile as rec

    monkeypatch.setattr(rec, "PLATFORMS", {"devto": object, "twitter": object, "ghost": object})
    monkeypatch.setattr(rec, "get_api_key", lambda n: "k" if n in ("devto", "twitter") else None)
    monkeypatch.setattr(rec, "get_platform_mode", lambda n: "manual" if n == "twitter" else "api")

    called = []

    def fake_reconcile_platform(name, **kw):
        called.append(name)
        return ReconcileReport(platform=name)

    monkeypatch.setattr(rec, "reconcile_platform", fake_reconcile_platform)
    rec.reconcile()
    # devto: keyed + api -> in; twitter: keyed but manual -> out; ghost: no key -> out
    assert called == ["devto"]


def test_reconcile_list_failure_sets_error_and_makes_no_writes(monkeypatch):
    """A platform API outage must NOT mass-soft-delete registry rows.

    If list_articles raises, the report carries the error with empty buckets
    and neither record_deletion nor record_publication is called, even with
    apply=True. Guards against deleting the whole registry during an outage.
    """
    import crier.reconcile as rec

    inst = MagicMock()
    inst.list_articles.side_effect = RuntimeError("API down")
    monkeypatch.setattr(rec, "get_platform_mode", lambda n: "api")
    monkeypatch.setattr(rec, "get_api_key", lambda n: "k")
    monkeypatch.setattr(rec, "get_platform", lambda n: (lambda _k: inst))
    monkeypatch.setattr(
        rec, "get_platform_publications",
        lambda n: [_row(platform_id="1", canonical_url="https://x/g/")],
    )
    rec_del = MagicMock()
    rec_pub = MagicMock()
    monkeypatch.setattr(rec, "record_deletion", rec_del)
    monkeypatch.setattr(rec, "record_publication", rec_pub)

    report = rec.reconcile_platform("devto", apply=True)
    assert report.error is not None
    assert "API down" in report.error
    assert report.gone_from_platform == []
    rec_del.assert_not_called()
    rec_pub.assert_not_called()
