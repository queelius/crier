"""Nostr platform: signed kind-1 notes broadcast to relays (NIP-01).

Nostr is a protocol, not a service: a note is a secp256k1/Schnorr-signed event
(BIP340) broadcast to relays over websockets. Signing needs the optional
[nostr] extra (pynostr, which pulls coincurve); the heavy import is deferred to
publish/delete so the platform stays importable and constructible without it.

api_key formats:
  - "nsec1..."                    bech32 private key, default relays
  - "<64-hex>"                    hex private key, default relays
  - "nsec1...|wss://r1,wss://r2"  key plus a custom relay list (pipe-separated)

Nostr has no authoritative cross-relay listing (a relay only holds what it has
seen), so list_articles/get_article are intentionally not implemented (empty/
None) and reconcile/stats do not apply. Notes are immutable, so update is not
supported. Deletion is best-effort via a NIP-09 (kind 5) event; relays may or
may not honor it.
"""

from __future__ import annotations

from typing import Any

from .base import Article, DeleteResult, Platform, PublishResult

DEFAULT_RELAYS = [
    "wss://relay.damus.io",
    "wss://nos.lol",
    "wss://relay.nostr.band",
    "wss://relay.primal.net",
]

_IMPORT_HINT = "Nostr requires the 'nostr' extra: pip install 'crier[nostr]'"


class Nostr(Platform):
    """Publish short notes to the Nostr network.

    Configure with a private key: ``crier config set platforms.nostr.api_key
    nsec1...`` (optionally ``nsec1...|wss://relay.a,wss://relay.b`` for custom
    relays). Short-form by convention (microblogging), though Nostr imposes no
    length limit.
    """

    name = "nostr"
    description = "Signed short notes on the Nostr protocol (relays)"
    max_content_length = None  # Nostr imposes no protocol length limit
    is_short_form = True
    supports_delete = True
    supports_stats = False
    api_key_url = "https://nostr.com/"

    def __init__(self, api_key: str, relays: list[str] | None = None):
        super().__init__(api_key)
        raw = api_key or ""
        if "|" in raw:
            key_part, relays_part = raw.split("|", 1)
            parsed = [r.strip() for r in relays_part.split(",") if r.strip()]
        else:
            key_part, parsed = raw, None
        self.secret = key_part.strip()
        self.relays = relays or parsed or list(DEFAULT_RELAYS)

    # --- helpers ---------------------------------------------------------

    def _load_key(self):
        """Build the pynostr PrivateKey (lazy import; raises if extra missing)."""
        try:
            from pynostr.key import PrivateKey
        except ImportError as e:  # pragma: no cover
            raise ImportError(_IMPORT_HINT) from e
        if self.secret.startswith("nsec"):
            return PrivateKey.from_nsec(self.secret)
        return PrivateKey.from_hex(self.secret)

    def _compose(self, article: Article) -> str:
        if article.is_rewrite:
            return self._append_canonical_url(article.body, article)
        parts = [article.title]
        if article.description:
            parts.append(article.description)
        if article.canonical_url:
            parts.append(article.canonical_url)
        if article.tags:
            parts.append(" ".join(f"#{t.replace('-', '')}" for t in article.tags[:5]))
        return "\n\n".join(parts)

    def _publish_event(self, event) -> None:
        """Broadcast a signed event to all configured relays."""
        try:
            from pynostr.relay_manager import RelayManager
        except ImportError as e:  # pragma: no cover
            raise ImportError(_IMPORT_HINT) from e
        rm = RelayManager(timeout=self.timeout)
        for url in self.relays:
            rm.add_relay(url)
        try:
            rm.publish_event(event)
            rm.run_sync()
        finally:
            try:
                rm.close_all_relay_connections()
            except Exception:
                pass

    # --- Platform interface ---------------------------------------------

    def publish(self, article: Article) -> PublishResult:
        text = self._compose(article)
        if error := self._check_content_length(text):
            return PublishResult(success=False, platform=self.name, error=error)
        try:
            from pynostr.event import Event

            priv = self._load_key()
            event = Event(content=text, kind=1, pubkey=priv.public_key.hex())
            event.sign(priv.hex())
            self._publish_event(event)
        except Exception as e:
            return PublishResult(success=False, platform=self.name, error=str(e))
        return PublishResult(
            success=True,
            platform=self.name,
            article_id=event.id,
            url=f"https://njump.me/{event.bech32()}",
        )

    def update(self, article_id: str, article: Article) -> PublishResult:
        return PublishResult(
            success=False,
            platform=self.name,
            error="Nostr notes are immutable; cannot update (post a new note).",
        )

    def list_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        # Nostr has no authoritative listing across relays; not supported.
        return []

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        return None

    def delete(self, article_id: str) -> DeleteResult:
        """Best-effort NIP-09 deletion: publish a kind-5 event referencing the note."""
        try:
            from pynostr.event import Event

            priv = self._load_key()
            event = Event(
                content="",
                kind=5,
                pubkey=priv.public_key.hex(),
                tags=[["e", article_id]],
            )
            event.sign(priv.hex())
            self._publish_event(event)
        except Exception as e:
            return DeleteResult(success=False, platform=self.name, error=str(e))
        return DeleteResult(success=True, platform=self.name)
