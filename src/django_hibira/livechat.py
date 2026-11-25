"""Hibira Live Chat on Django pages, with verified signed-in users.

``{% load hibira %}{% hibira_live_chat %}`` before ``</body>`` puts the chat
widget on the page. With ``HIBIRA["LIVECHAT_IDENTITY_SECRET"]`` set (Live
Chat › Settings › Widget › Verified visitors), a signed-in user chats as
themselves: their ID is signed with the secret, so the inbox shows their name
and email and nobody can pretend to be them.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from .conf import get_settings

SCRIPT_URL = "https://chat.hibira.io/w/v1.js"


def user_hash(identity_secret: str, user_id: Any) -> str:
    """hex(HMAC-SHA256(identity secret, user ID)), the widget's data-user-hash."""
    if not identity_secret:
        raise ValueError("user_hash: identity_secret is required")
    return hmac.new(identity_secret.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()


def identity(user: Any) -> dict[str, str] | None:
    """The verified-visitor fields for a Django user ({id, hash, name, email}),
    or None for anonymous users or without an identity secret. Hand it to an
    SPA and call ``HibiraLiveChat.identify(it)``."""
    secret = get_settings().livechat_identity_secret
    if not secret or user is None or not getattr(user, "is_authenticated", False) or user.pk is None:
        return None
    full = user.get_full_name() if hasattr(user, "get_full_name") else ""
    name = full or (user.get_username() if hasattr(user, "get_username") else "")
    out = {"id": str(user.pk), "hash": user_hash(secret, user.pk)}
    if name:
        out["name"] = str(name)
    email = getattr(user, "email", "")
    if email:
        out["email"] = str(email)
    return out


def attributes(
    request: Any = None,
    workspace: str | None = None,
    color: str | None = None,
    lang: str | None = None,
    launcher: bool = True,
) -> dict[str, str]:
    """The widget script tag's attributes (src and data-*)."""
    ws = workspace or get_settings().livechat_workspace
    if not ws:
        return {}
    attrs = {"src": SCRIPT_URL, "data-workspace": ws}
    if color:
        attrs["data-color"] = color
    if lang:
        attrs["data-lang"] = lang
    if not launcher:
        attrs["data-launcher"] = "none"
    who = identity(getattr(request, "user", None)) if request is not None else None
    if who:
        attrs["data-user-id"] = who["id"]
        attrs["data-user-hash"] = who["hash"]
        if "name" in who:
            attrs["data-user-name"] = who["name"]
        if "email" in who:
            attrs["data-user-email"] = who["email"]
    return attrs
