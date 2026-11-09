"""Waiting rooms: send visitors to the Hibira queue, let them in with a pass.

Protect a view::

    from django_hibira.waiting_room import waiting_room

    @waiting_room("presale")
    def drop(request):
        request.hibira_pass  # {"number": 42, "ticket_id": "...", ...}

Or whole path prefixes, with ``django_hibira.waiting_room.WaitingRoomMiddleware``
in ``MIDDLEWARE`` and ``HIBIRA["WAITING_ROOMS"] = {"/drop/": "presale"}``.

A visitor without a valid pass is redirected to the hosted waiting page
(non-GET requests get a 403). When it's their turn the page sends them back
with ``?hibira_pass=...``, which is checked, stored in an HttpOnly cookie
(``hibira_wr_<room>``), and removed from the URL.
"""

from __future__ import annotations

import base64
import binascii
import functools
import hashlib
import hmac
import json
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse

from .conf import get_settings

PURPOSE = b"hibira-waitroom-pass."
PARAM = "hibira_pass"


@dataclass(frozen=True)
class Pass:
    app_id: str
    room: str
    number: int
    ticket_id: str
    issued_at: int
    expires_at: int


def _b64decode(value: str) -> bytes | None:
    if not value or not all(c.isalnum() or c in "-_" for c in value):
        return None
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError):
        return None


def verify_pass(
    token: str | None,
    secret: str | Iterable[str],
    room: str | None = None,
    app_id: str | None = None,
    now: float | None = None,
) -> Pass | None:
    """Returns the pass's claims, or None when it is missing, forged, expired,
    or for another room or app. ``secret`` may be a list during a rotation."""
    if not isinstance(token, str) or len(token) > 1024 or token.count(".") != 1:
        return None
    payload, _, sig_part = token.partition(".")
    sig = _b64decode(sig_part)
    if not payload or sig is None or len(sig) != 32:
        return None
    secrets = [secret] if isinstance(secret, str) else list(secret)
    message = PURPOSE + payload.encode()
    if not any(
        hmac.compare_digest(hmac.new(s.encode(), message, hashlib.sha256).digest(), sig) for s in secrets if s
    ):
        return None
    raw = _b64decode(payload)
    try:
        claims = json.loads(raw) if raw else None
    except ValueError:
        return None
    if not isinstance(claims, dict) or claims.get("v") != 1:
        return None
    exp = claims.get("exp")
    if not isinstance(exp, (int, float)) or (time.time() if now is None else now) >= exp:
        return None
    if room is not None and claims.get("room") != room:
        return None
    if app_id is not None and claims.get("app") != app_id:
        return None
    return Pass(
        app_id=claims.get("app", ""),
        room=claims.get("room", ""),
        number=claims.get("n", 0),
        ticket_id=claims.get("tid", ""),
        issued_at=claims.get("iat", 0),
        expires_at=int(exp),
    )


def _default_host() -> str:
    s = get_settings()
    scheme = "https" if s.use_tls else "http"
    port = "" if s.port == (443 if s.use_tls else 80) else f":{s.port}"
    return f"{scheme}://{s.host}{port}"


def waiting_room_url(room: str, return_url: str | None = None, *, app_key: str | None = None,
                     host: str | None = None, lang: str | None = None) -> str:
    """The hosted waiting page address for a room."""
    key = app_key or get_settings().key or ""
    url = f"{(host or _default_host()).rstrip('/')}/wait/{quote(key, safe='')}/{quote(room, safe='')}"
    query = {k: v for k, v in (("return", return_url), ("lang", lang)) if v}
    return url + ("?" + urlencode(query) if query else "")


def _without_pass(request: HttpRequest) -> str:
    query = [(k, v) for k, v in parse_qsl(request.META.get("QUERY_STRING", ""), keep_blank_values=True) if k != PARAM]
    return request.build_absolute_uri(request.path) + ("?" + urlencode(query) if query else "")


def check(request: HttpRequest, room: str, *, secret: str | Iterable[str] | None = None,
          app_key: str | None = None, host: str | None = None, lang: str | None = None,
          cookie_name: str | None = None) -> HttpResponse | None:
    """Returns None to let the request through (and sets ``request.hibira_pass``),
    or the response to send instead: a redirect to the queue, a redirect that
    stores a fresh pass, or a 403 for a non-GET request without a pass."""
    s = get_settings()
    secret = secret or s.secret
    if not secret:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured("Waiting rooms need HIBIRA_APP_SECRET.")
    name = cookie_name or f"hibira_wr_{room}"
    app_id = s.app_id

    fresh = request.GET.get(PARAM)
    if fresh:
        claims = verify_pass(fresh, secret, room=room, app_id=app_id)
        if claims:
            response = HttpResponseRedirect(_without_pass(request))
            response.set_cookie(name, fresh, max_age=max(0, int(claims.expires_at - time.time())), path="/",
                                secure=request.is_secure(), httponly=True, samesite="Lax")
            response["Cache-Control"] = "no-store"
            return response

    claims = verify_pass(request.COOKIES.get(name), secret, room=room, app_id=app_id)
    if claims:
        request.hibira_pass = claims  # type: ignore[attr-defined]
        return None
    if request.method not in ("GET", "HEAD"):
        response = JsonResponse({"error": "waiting_room", "message": "join the waiting room first"}, status=403)
    else:
        response = HttpResponseRedirect(
            waiting_room_url(room, _without_pass(request), app_key=app_key, host=host, lang=lang)
        )
    response["Cache-Control"] = "no-store"
    return response


def waiting_room(room: str, **options: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """View decorator: only visitors with a valid pass for ``room`` get in."""

    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(view)
        def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
            blocked = check(request, room, **options)
            return blocked if blocked is not None else view(request, *args, **kwargs)

        return wrapped

    return decorator


class WaitingRoomMiddleware:
    """Protects the path prefixes in ``HIBIRA["WAITING_ROOMS"]``, a dict of
    ``{"/drop/": "presale"}``. The longest matching prefix wins."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        rooms = get_settings().waiting_rooms
        match = max((p for p in rooms if request.path.startswith(p)), key=len, default=None)
        if match is not None:
            blocked = check(request, rooms[match])
            if blocked is not None:
                return blocked
        return self.get_response(request)


__all__ = ["Pass", "WaitingRoomMiddleware", "check", "verify_pass", "waiting_room", "waiting_room_url"]
