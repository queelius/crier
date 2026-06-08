"""Tests for the Nostr platform.

Parsing/property tests run without the optional [nostr] extra; the signing
tests importorskip pynostr and exercise real BIP340 signatures with the relay
broadcast mocked out.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from crier.platforms.base import Article
from crier.platforms.nostr import DEFAULT_RELAYS, Nostr


def _article(**kw):
    base = dict(title="T", body="hello world", canonical_url="https://x/p/")
    base.update(kw)
    return Article(**base)


# --- construction / parsing (no extra needed) ---------------------------


def test_properties():
    n = Nostr("nsec1abc")
    assert n.name == "nostr"
    assert n.is_short_form is True
    assert n.max_content_length is None
    assert n.supports_delete is True
    assert n.supports_stats is False


def test_default_relays():
    n = Nostr("nsec1abc")
    assert n.relays == DEFAULT_RELAYS
    assert n.secret == "nsec1abc"


def test_custom_relays_via_pipe():
    n = Nostr("nsec1abc|wss://relay.one,wss://relay.two")
    assert n.secret == "nsec1abc"
    assert n.relays == ["wss://relay.one", "wss://relay.two"]


def test_relays_kwarg_overrides():
    n = Nostr("nsec1abc", relays=["wss://only.relay"])
    assert n.relays == ["wss://only.relay"]


def test_update_not_supported():
    res = Nostr("nsec1abc").update("id", _article())
    assert res.success is False
    assert "immutable" in res.error


def test_list_articles_empty():
    assert Nostr("nsec1abc").list_articles() == []


def test_get_article_none():
    assert Nostr("nsec1abc").get_article("x") is None


# --- signing / publish (needs the [nostr] extra) ------------------------


def test_publish_signs_and_returns_njump_url():
    pytest.importorskip("pynostr")
    from pynostr.key import PrivateKey

    captured = {}
    n = Nostr(PrivateKey().hex())
    with patch.object(Nostr, "_publish_event", lambda self, e: captured.update(event=e)):
        res = n.publish(_article(body="my short take", is_rewrite=True))
    assert res.success is True
    ev = captured["event"]
    assert ev.verify() is True  # real BIP340 signature
    assert ev.kind == 1
    assert "my short take" in ev.content
    assert "https://x/p/" in ev.content  # canonical appended
    assert res.article_id == ev.id
    assert res.url.startswith("https://njump.me/note1")


def test_publish_composes_from_metadata_when_not_rewrite():
    pytest.importorskip("pynostr")
    from pynostr.key import PrivateKey

    captured = {}
    n = Nostr(PrivateKey().hex())
    with patch.object(Nostr, "_publish_event", lambda self, e: captured.update(event=e)):
        res = n.publish(
            _article(title="My Post", description="A desc",
                     tags=["python", "x"], is_rewrite=False)
        )
    assert res.success
    c = captured["event"].content
    assert "My Post" in c and "A desc" in c and "#python" in c


def test_delete_publishes_kind5():
    pytest.importorskip("pynostr")
    from pynostr.key import PrivateKey

    captured = {}
    n = Nostr(PrivateKey().hex())
    with patch.object(Nostr, "_publish_event", lambda self, e: captured.update(event=e)):
        res = n.delete("event-id-123")
    assert res.success is True
    ev = captured["event"]
    assert ev.kind == 5
    assert ev.verify() is True
    assert ["e", "event-id-123"] in ev.tags


def test_publish_missing_extra_returns_failure(monkeypatch):
    pytest.importorskip("pynostr")

    def boom(self):
        raise ImportError("Nostr requires the 'nostr' extra")

    monkeypatch.setattr(Nostr, "_load_key", boom)
    res = Nostr("nsec1abc").publish(_article(body="x", is_rewrite=True))
    assert res.success is False
    assert "extra" in res.error
