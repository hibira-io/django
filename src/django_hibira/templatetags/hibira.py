"""Template tags. Load them with ``{% load hibira %}``.

- ``{% hibira_scripts %}`` in ``<head>``: connection settings plus the
  pusher-js and django-hibira scripts.
- ``{% hibira_stream room %}``: makes this page apply what is broadcast to
  the stream.
- ``{% dom_id message %}``: the element ID broadcasts target, ``message_12``.
"""

from __future__ import annotations

from typing import Any

from django import template
from django.middleware.csrf import get_token
from django.templatetags.static import static
from django.urls import NoReverseMatch, reverse
from django.utils.html import format_html, format_html_join

from .. import streams
from ..conf import get_settings

register = template.Library()


def _url(name: str, fallback: str) -> str:
    try:
        return reverse(name)
    except NoReverseMatch:
        return fallback


@register.simple_tag(takes_context=True)
def hibira_scripts(context: template.Context, pusher: bool = True) -> str:
    """Meta tags with the public connection settings (the app key, never the
    secret) and the scripts. Pass ``pusher=False`` if you load pusher-js
    yourself (it must set ``window.Pusher``)."""
    s = get_settings()
    meta = [
        ("hibira-key", s.key or ""),
        ("hibira-host", s.host),
        ("hibira-port", str(s.port)),
        ("hibira-tls", "true" if s.use_tls else "false"),
        ("hibira-stream-auth-endpoint", _url("hibira:stream_auth", "/hibira/streams/auth")),
        ("hibira-auth-endpoint", _url("hibira:channel_auth", "/hibira/auth")),
    ]
    request = context.get("request")
    if request is not None:
        # For POST /hibira/auth, which CSRF protection covers.
        meta.append(("hibira-csrf-token", get_token(request)))
    tags = format_html_join("\n", '<meta name="{}" content="{}">', meta)
    scripts = []
    if pusher:
        scripts.append(format_html('<script src="{}" defer></script>', static("django_hibira/vendor/pusher.min.js")))
    scripts.append(format_html('<script src="{}" defer></script>', static("django_hibira/hibira.js")))
    return format_html("{}\n{}", tags, format_html_join("\n", "{}", ((s,) for s in scripts)))


@register.simple_tag
def hibira_stream(*streamables: Any, **attrs: Any) -> str:
    """``<hibira-stream>`` subscribes the page to a stream and applies every
    operation broadcast to it. Extra keyword arguments become attributes."""
    name = streams.stream_name(*streamables)
    extra = format_html_join("", ' {}="{}"', ((k.replace("_", "-"), v) for k, v in attrs.items()))
    return format_html(
        '<hibira-stream channel="{}" signed-stream="{}"{}></hibira-stream>',
        streams.channel_name(name),
        streams.sign_stream(name),
        extra,
    )


@register.simple_tag
def dom_id(obj: Any, prefix: str | None = None) -> str:
    return streams.dom_id(obj, prefix)


@register.simple_tag
def stream_name(*streamables: Any) -> str:
    return streams.stream_name(*streamables)
