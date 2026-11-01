"""Broadcast a model's changes to the pages watching it.

::

    from django_hibira import broadcasts

    @broadcasts(to="room", target="messages")
    class Message(models.Model):
        room = models.ForeignKey(Room, on_delete=models.CASCADE)
        body = models.TextField()

Creating a message renders ``chat/_message.html`` (with the message as
``message``) and appends it to ``#messages`` on every page that has
``{% hibira_stream room %}``; saving it again replaces ``#message_<pk>``, and
deleting it removes that element. The partial's root element must carry
``id="{% dom_id message %}"``.

``broadcasts(to="room", refresh=True)`` sends a page refresh instead of
fragments: the simplest way to make a page live, at the cost of a fetch per
change.
"""

from __future__ import annotations

from typing import Any, Callable

from django.db import models
from django.db.models.signals import post_delete, post_save

from . import streams

_registry: dict[type[models.Model], dict[str, Any]] = {}


def broadcasts(
    to: str | Callable[[Any], Any] | None = None,
    *,
    target: str | None = None,
    template: str | None = None,
    context_name: str | None = None,
    insert: str = "append",
    refresh: bool = False,
    on: tuple[str, ...] = ("create", "update", "delete"),
) -> Callable[[type[models.Model]], type[models.Model]]:
    """Class decorator that broadcasts creates, updates and deletes.

    ``to`` names the stream: an attribute path (``"room"``,
    ``"room.workspace"``), a callable taking the instance, or None for the
    model class itself (``{% hibira_stream "chat.message" %}``).
    ``target`` is the list element new rows go into (default: the model's
    plural name, ``messages``); ``insert`` is ``"append"`` or ``"prepend"``.
    """
    if insert not in ("append", "prepend"):
        raise ValueError('insert must be "append" or "prepend"')
    unknown = set(on) - {"create", "update", "delete"}
    if unknown:
        raise ValueError(f"Unknown events in on=: {', '.join(sorted(unknown))}")

    def decorate(model: type[models.Model]) -> type[models.Model]:
        meta = model._meta
        _registry[model] = {
            "to": to,
            "target": target or str(meta.verbose_name_plural).replace(" ", "_").lower(),
            "template": template or f"{meta.app_label}/_{meta.model_name}.html",
            "context_name": context_name or meta.model_name,
            "insert": insert,
            "refresh": refresh,
            "on": tuple(on),
        }
        uid = f"django_hibira:{meta.label_lower}"
        post_save.connect(_saved, sender=model, weak=False, dispatch_uid=uid + ":save")
        post_delete.connect(_deleted, sender=model, weak=False, dispatch_uid=uid + ":delete")
        return model

    return decorate


def stream_for(instance: models.Model) -> Any:
    """The streamable a registered instance broadcasts to."""
    options = _registry[type(instance)]
    to = options["to"]
    if to is None:
        return type(instance)
    if callable(to):
        return to(instance)
    value: Any = instance
    for attr in str(to).split("."):
        value = getattr(value, attr)
    return value


def _saved(sender: type[models.Model], instance: models.Model, created: bool, raw: bool = False, **kwargs: Any) -> None:
    options = _registry.get(sender)
    if options is None or raw:
        return
    event = "create" if created else "update"
    if event not in options["on"]:
        return
    stream = stream_for(instance)
    if stream is None:
        return
    if options["refresh"]:
        streams.broadcast_refresh(stream)
        return
    context = {options["context_name"]: instance}
    if created:
        streams.broadcast(stream, action=options["insert"], target=options["target"],
                          template=options["template"], context=context)
    else:
        streams.broadcast_replace(stream, target=instance, template=options["template"], context=context)


def _deleted(sender: type[models.Model], instance: models.Model, **kwargs: Any) -> None:
    options = _registry.get(sender)
    if options is None or "delete" not in options["on"]:
        return
    try:
        stream = stream_for(instance)
    except models.ObjectDoesNotExist:
        # The parent went first (a cascade); its own page is gone anyway.
        return
    if stream is None:
        return
    if options["refresh"]:
        streams.broadcast_refresh(stream)
    else:
        streams.broadcast_remove(stream, target=streams.dom_id(instance))
