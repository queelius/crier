"""Mastodon platform: Mastodon-API-compatible fediverse server.

Implements the original Mastodon network. Defaults to ``mastodon.social``;
other instances are addressed via the ``instance:access_token`` api_key
shape, identical to prior crier behavior.

All request logic lives on ``FediversePlatform``; this class is a thin
configuration wrapper. Pleroma, Akkoma, GoToSocial, and other
Mastodon-API-compatible servers are siblings of this class, each defining
their own defaults but sharing the same parent.
"""

from __future__ import annotations

from ._fediverse import FediversePlatform


class Mastodon(FediversePlatform):
    """Mastodon publishing platform (Mastodon-API-compatible).

    api_key shape: ``"instance.host:access_token"`` (e.g.
    ``"mastodon.social:token123"``) or just the access token if
    ``instance`` is supplied separately. Defaults to ``mastodon.social``
    when only a bare token is provided.
    """

    name = "mastodon"
    description = "Short posts (500 chars)"
    max_content_length = 500
    default_instance = "mastodon.social"
