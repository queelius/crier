"""Pleroma platform: Pleroma fediverse server (Mastodon-API-compatible).

Pleroma is a separate fediverse server implementation that exposes a
Mastodon-compatible REST API. Its sibling fork **Akkoma** is API-identical
for crier's purposes; users with Akkoma instances can use this platform
unchanged or define their own ``Akkoma`` class with a different
``description`` and the same parent.

Pleroma instances vary widely in character limits. The class default of
5000 reflects upstream Pleroma's default; many operators raise it
(common to see 65535, effectively unlimited). If your instance exposes a
larger limit, override ``max_content_length`` on the subclass or
instance.
"""

from __future__ import annotations

from ._fediverse import FediversePlatform


class Pleroma(FediversePlatform):
    """Pleroma fediverse server.

    Pleroma instances are user-operated; there is no canonical hostname.
    Configure via the ``instance:access_token`` api_key shape or by
    setting an explicit instance.
    """

    name = "pleroma"
    description = "Short posts (5000 chars default) on Pleroma fediverse server"
    max_content_length = 5000
    default_instance = None  # Must be configured per user's instance
