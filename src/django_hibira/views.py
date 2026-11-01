"""The endpoints browsers and Hibira call. Include them with::

    path("hibira/", include("django_hibira.urls")),
"""

from __future__ import annotations

import hmac
import logging
from typing import Any

import hibira
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import signals, streams
from .client import get_client
from .conf import get_settings

logger = logging.getLogger("django_hibira")

SIGNATURE_HEADERS = ("HTTP_X_PUSHER_SIGNATURE", "HTTP_X_HIBIRA_PREVIOUS_SIGNATURE")


@csrf_exempt
@require_POST
def stream_auth(request: HttpRequest) -> HttpResponse:
    """Signs a subscription to a stream channel.

    The signed stream name that ``{% hibira_stream %}`` rendered is the
    credential, so this needs no session and no CSRF token.
    """
    channel = request.POST.get("channel_name", "")
    socket_id = request.POST.get("socket_id", "")
    name = streams.unsign_stream(request.POST.get("signed_stream_name", ""))
    if name is None or not hmac.compare_digest(channel, streams.channel_name(name)):
        return HttpResponseForbidden()
    try:
        return JsonResponse(get_client().authenticate_channel(channel, socket_id))
    except hibira.HibiraError:
        return HttpResponseBadRequest()


@require_POST
def channel_auth(request: HttpRequest) -> HttpResponse:
    """Signs subscriptions to your own private- and presence- channels.

    Calls ``HIBIRA["AUTHORIZE_CHANNEL"](request, channel_name)``: return a
    falsy value to refuse, True to allow a private channel, or a dict such as
    ``{"user_id": request.user.pk, "user_info": {"name": ...}}`` for a
    presence channel. CSRF protection applies, as in the rest of your site.
    """
    channel = request.POST.get("channel_name", "")
    socket_id = request.POST.get("socket_id", "")
    authorize = get_settings().authorize_channel
    if authorize is None or streams.is_stream_channel(channel):
        return HttpResponseForbidden()
    if not channel.startswith(("private-", "presence-")):
        return HttpResponseForbidden()

    result = authorize(request, channel)
    if not result:
        return HttpResponseForbidden()

    try:
        if channel.startswith("presence-"):
            if not isinstance(result, dict) or result.get("user_id") in (None, ""):
                return HttpResponseForbidden()
            user_data = {"user_id": str(result["user_id"]), "user_info": result.get("user_info") or {}}
            return JsonResponse(get_client().authenticate_channel(channel, socket_id, user_data))
        return JsonResponse(get_client().authenticate_channel(channel, socket_id))
    except hibira.HibiraError:
        return HttpResponseBadRequest()


@csrf_exempt
@require_POST
def webhooks(request: HttpRequest) -> HttpResponse:
    """Receives Hibira webhooks. Add this URL on your app page → Webhooks.

    Each event is sent as the ``webhook_received`` signal. While a rotated
    secret is in its grace period, X-Hibira-Previous-Signature carries the
    HMAC made with the old one, so either header is accepted.
    """
    s = get_settings()
    if not s.configured:
        return HttpResponseForbidden()
    key = request.META.get("HTTP_X_PUSHER_KEY", "")
    body = request.body
    payload: dict[str, Any] | None = None
    for header in SIGNATURE_HEADERS:
        signature = request.META.get(header)
        if not signature:
            continue
        try:
            payload = get_client().verify_webhook(key, signature, body)
            break
        except hibira.InvalidWebhook:
            continue
        except ValueError:
            return HttpResponseBadRequest()
    if payload is None:
        return HttpResponse(status=401)

    time_ms = payload.get("time_ms")
    for event in payload.get("events") or []:
        if not isinstance(event, dict) or not isinstance(event.get("name"), str):
            continue
        signals.webhook_received.send(sender=webhooks, name=event["name"], event=event, time_ms=time_ms)
    return HttpResponse(status=200)


@require_GET
def push_token(request: HttpRequest) -> HttpResponse:
    """Returns a push user token for the signed-in user (setUserId in the
    web, Android and iOS push SDKs). The SDKs pass ``?user_id=``, which must
    be the signed-in user's push user ID."""
    s = get_settings()
    if not s.push_configured:
        return HttpResponse(status=404)
    resolve = s.push_user_id or _default_push_user_id
    user_id = resolve(request)
    if user_id in (None, ""):
        return HttpResponse(status=401)
    user_id = str(user_id)
    if not hmac.compare_digest(user_id, request.GET.get("user_id", "")):
        return HttpResponse(status=401)
    return JsonResponse(get_client().push_token(user_id))


def _default_push_user_id(request: HttpRequest) -> Any:
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    return user.pk


__all__ = ["stream_auth", "channel_auth", "webhooks", "push_token"]
