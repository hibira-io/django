"""Live HTML over Hibira.

A *stream* is a name for something pages can watch: a model instance, a
string, or several of them together (``stream_name(room, "typing")``). Each
stream maps to one private Hibira channel. A page subscribes with
``{% hibira_stream room %}``, which renders the stream name signed with your
``SECRET_KEY``, so a browser can only watch the streams your views rendered
for it.

The server sends small HTML operations to a stream (append this fragment to
``#messages``, replace ``#message_12``, remove it, refresh the page) and the
``django_hibira/hibira.js`` script applies them to every open page.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Iterable

import hibira
from django.core import signing
from django.db import models, transaction
from django.template.loader import render_to_string

from . import testing
from .client import get_client
from .conf import get_settings

logger = logging.getLogger("django_hibira")

EVENT = "html-swap"
CHANNEL_PREFIX = "private-stream-"
SIGNING_SALT = "django_hibira.stream"
ACTIONS = ("append", "prepend", "replace", "update", "before", "after", "remove", "refresh")


def stream_name(*streamables: Any) -> str:
    """Joins model instances, model classes and strings into a stream name.

    ``stream_name(room)`` is ``"chat.room:5"``, ``stream_name(room, "typing")``
    is ``"chat.room:5:typing"`` and ``stream_name(Message)`` is
    ``"chat.message"``.
    """
    parts = [_part(s) for s in _flatten(streamables)]
    parts = [p for p in parts if p]
    if not parts:
        raise ValueError("A stream needs at least one non-blank streamable")
    return ":".join(parts)


def channel_name(stream: Any) -> str:
    """The private channel a stream maps to.

    Stream names hold characters channel names can't, so the channel is
    named after a digest of the stream name.
    """
    name = stream if isinstance(stream, str) else stream_name(stream)
    return CHANNEL_PREFIX + hashlib.sha256(name.encode()).hexdigest()


def is_stream_channel(name: str) -> bool:
    return name.startswith(CHANNEL_PREFIX)


def sign_stream(name: str) -> str:
    return signing.Signer(salt=SIGNING_SALT).sign(name)


def unsign_stream(value: str) -> str | None:
    try:
        return signing.Signer(salt=SIGNING_SALT).unsign(value)
    except signing.BadSignature:
        return None


def dom_id(obj: Any, prefix: str | None = None) -> str:
    """The element ID for a model instance: ``message_12``, or
    ``new_message`` for an unsaved one. With a prefix: ``edit_message_12``.
    """
    if isinstance(obj, type) and issubclass(obj, models.Model):
        base = f"new_{obj._meta.model_name}"
    elif isinstance(obj, models.Model):
        base = f"{obj._meta.model_name}_{obj.pk}" if obj.pk is not None else f"new_{obj._meta.model_name}"
    else:
        base = str(obj)
    return f"{prefix}_{base}" if prefix else base


def broadcast(
    *streamables: Any,
    action: str,
    target: Any = None,
    targets: str | None = None,
    html: str | None = None,
    template: str | None = None,
    context: dict[str, Any] | None = None,
    socket_id: str | None = None,
    on_commit: bool | None = None,
) -> None:
    """Sends one HTML operation to every page watching the stream.

    ``target`` is an element ID (or a model instance, for its ``dom_id``);
    ``targets`` is a CSS selector for several elements. The fragment comes
    from ``html``, or from ``template`` rendered with ``context``.
    ``socket_id`` skips the browser that made the change.
    """
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {', '.join(ACTIONS)}")
    if action != "refresh" and target is None and targets is None:
        raise ValueError(f"{action} needs a target (element ID) or targets (CSS selector)")

    name = stream_name(*streamables)
    settings = get_settings()

    def send() -> None:
        payload: dict[str, Any] = {"action": action}
        if target is not None:
            payload["target"] = dom_id(target) if isinstance(target, models.Model) else str(target)
        if targets is not None:
            payload["targets"] = targets
        if action not in ("remove", "refresh"):
            payload["html"] = html if html is not None else render_to_string(template, context or {}) if template else ""
        _send(name, payload, socket_id)

    defer = settings.on_commit if on_commit is None else on_commit
    if defer:
        transaction.on_commit(send)
    else:
        send()


def broadcast_append(*streamables: Any, **kwargs: Any) -> None:
    broadcast(*streamables, action="append", **kwargs)


def broadcast_prepend(*streamables: Any, **kwargs: Any) -> None:
    broadcast(*streamables, action="prepend", **kwargs)


def broadcast_replace(*streamables: Any, **kwargs: Any) -> None:
    broadcast(*streamables, action="replace", **kwargs)


def broadcast_update(*streamables: Any, **kwargs: Any) -> None:
    broadcast(*streamables, action="update", **kwargs)


def broadcast_before(*streamables: Any, **kwargs: Any) -> None:
    broadcast(*streamables, action="before", **kwargs)


def broadcast_after(*streamables: Any, **kwargs: Any) -> None:
    broadcast(*streamables, action="after", **kwargs)


def broadcast_remove(*streamables: Any, **kwargs: Any) -> None:
    broadcast(*streamables, action="remove", **kwargs)


def broadcast_refresh(*streamables: Any, **kwargs: Any) -> None:
    """Tells every page watching the stream to fetch itself again."""
    broadcast(*streamables, action="refresh", **kwargs)


def trigger(
    channels: str | list[str],
    event: str,
    data: Any,
    *,
    socket_id: str | None = None,
    on_commit: bool | None = None,
) -> None:
    """Sends a plain event to your own channels (``private-orders``,
    ``presence-room.1``, ``public-scores``), after the transaction commits
    unless ``on_commit=False``. Errors are logged, not raised; call
    ``django_hibira.get_client().trigger(...)`` to handle them yourself.
    """
    settings = get_settings()

    def send() -> None:
        if testing.record(channels, event, data, socket_id):
            return
        if not get_settings().active:
            return
        try:
            get_client().trigger(channels, event, data, socket_id=socket_id)
        except Exception:  # a realtime hiccup must not break the request that saved the data
            logger.exception("Hibira: event %r to %r failed", event, channels)

    defer = settings.on_commit if on_commit is None else on_commit
    if defer:
        transaction.on_commit(send)
    else:
        send()


def _send(name: str, payload: dict[str, Any], socket_id: str | None) -> None:
    channel = channel_name(name)
    if testing.record(channel, EVENT, payload, socket_id, stream=name):
        return
    settings = get_settings()
    if not settings.active:
        return
    try:
        get_client().trigger(channel, EVENT, payload, socket_id=socket_id)
    except hibira.PayloadTooLarge:
        _oversized(name, channel, payload, socket_id, settings.oversize)
    except Exception:  # a realtime hiccup must not break the request that saved the data
        logger.exception("Hibira: %s broadcast to stream %r failed", payload["action"], name)


def _oversized(name: str, channel: str, payload: dict[str, Any], socket_id: str | None, mode: str) -> None:
    size = len(json.dumps(payload).encode())
    message = f"Hibira: {payload['action']} broadcast to stream {name!r} is {size} bytes, over the app's event size limit"
    if mode == "raise":
        raise hibira.PayloadTooLarge(413, message, None)
    if mode == "refresh" and payload["action"] != "refresh":
        logger.warning("%s; sent a page refresh instead", message)
        try:
            get_client().trigger(channel, EVENT, {"action": "refresh"}, socket_id=socket_id)
        except Exception:
            logger.exception("Hibira: refresh to stream %r failed", name)
    else:
        logger.warning("%s; dropped", message)


def _flatten(items: Iterable[Any]) -> Iterable[Any]:
    for item in items:
        if isinstance(item, (list, tuple)):
            yield from _flatten(item)
        elif item is not None:
            yield item


def _part(item: Any) -> str:
    if isinstance(item, type) and issubclass(item, models.Model):
        return item._meta.label_lower
    if isinstance(item, models.Model):
        if item.pk is None:
            raise ValueError(f"Can't stream an unsaved {item._meta.label}")
        return f"{item._meta.label_lower}:{item.pk}"
    if hasattr(item, "to_stream_name"):
        return str(item.to_stream_name())
    return str(item).strip()
