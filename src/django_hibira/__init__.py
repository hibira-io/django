"""Realtime for Django over Hibira: no Channels, ASGI server or Redis."""

from __future__ import annotations

from typing import Any

from .broadcasting import broadcasts
from .signals import on_webhook, webhook_received
from .streams import (
    broadcast,
    broadcast_after,
    broadcast_append,
    broadcast_before,
    broadcast_prepend,
    broadcast_refresh,
    broadcast_remove,
    broadcast_replace,
    broadcast_update,
    channel_name,
    dom_id,
    stream_name,
    trigger,
)

__version__ = "0.1.0"


def get_client() -> Any:
    """The shared ``hibira.Client`` for the HIBIRA settings."""
    from .client import get_client as _get_client

    return _get_client()


def socket_id(request: Any) -> str | None:
    """The Hibira socket ID of the browser that sent this request (htmx
    requests carry it in X-Hibira-Socket-Id; a form can post it as
    ``hibira_socket_id``). Pass it to a broadcast to skip that browser."""
    value = request.headers.get("X-Hibira-Socket-Id")
    if not value and request.method == "POST":
        value = request.POST.get("hibira_socket_id")
    return value or None


__all__ = [
    "broadcast",
    "broadcast_after",
    "broadcast_append",
    "broadcast_before",
    "broadcast_prepend",
    "broadcast_refresh",
    "broadcast_remove",
    "broadcast_replace",
    "broadcast_update",
    "broadcasts",
    "channel_name",
    "dom_id",
    "get_client",
    "on_webhook",
    "socket_id",
    "stream_name",
    "trigger",
    "webhook_received",
]
