"""The shared hibira.Client, built from the HIBIRA setting."""

from __future__ import annotations

import threading
from typing import Any

import hibira
from django.core.exceptions import ImproperlyConfigured

from .conf import Settings, get_settings

_lock = threading.Lock()
_cache: dict[str, Any] = {}


def _signature(s: Settings) -> tuple[Any, ...]:
    return (
        s.app_id, s.key, s.secret, s.host, s.port, s.use_tls,
        s.push_instance_id, s.push_secret_key, s.push_endpoint,
        tuple(sorted(s.client_options.items())),
    )


def get_client() -> hibira.Client:
    """Returns a hibira.Client for the current settings.

    The client is reused while the settings stay the same, and rebuilt when
    they change (override_settings in tests, for example).
    """
    s = get_settings()
    if not s.configured:
        raise ImproperlyConfigured(
            f"Hibira is not configured: set {', '.join(s.missing)} "
            "(environment variables or the HIBIRA setting). "
            "Copy them from your app page on https://hibira.io/portal."
        )
    key = _signature(s)
    with _lock:
        if _cache.get("signature") != key:
            _cache["client"] = hibira.Client(
                s.app_id,
                s.key,
                s.secret,
                host=s.host,
                port=s.port,
                use_tls=s.use_tls,
                push_instance_id=s.push_instance_id,
                push_secret_key=s.push_secret_key,
                push_endpoint=s.push_endpoint,
                **s.client_options,
            )
            _cache["signature"] = key
        return _cache["client"]
