"""Settings for django-hibira.

Everything lives in one ``HIBIRA`` dict in your Django settings. Each
connection setting falls back to an environment variable, so a project that
sets ``HIBIRA_APP_ID``, ``HIBIRA_APP_KEY`` and ``HIBIRA_APP_SECRET`` needs no
``HIBIRA`` dict at all::

    HIBIRA = {
        "APP_ID": "...",
        "KEY": "...",
        "SECRET": "...",
        "AUTHORIZE_CHANNEL": "myapp.realtime.authorize",
    }
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from django.conf import settings as django_settings
from django.utils.module_loading import import_string

#: Setting name -> environment variable it falls back to.
ENV = {
    "APP_ID": "HIBIRA_APP_ID",
    "KEY": "HIBIRA_APP_KEY",
    "SECRET": "HIBIRA_APP_SECRET",
    "HOST": "HIBIRA_HOST",
    "PORT": "HIBIRA_PORT",
    "USE_TLS": "HIBIRA_USE_TLS",
    "PUSH_INSTANCE_ID": "HIBIRA_PUSH_INSTANCE_ID",
    "PUSH_SECRET_KEY": "HIBIRA_PUSH_SECRET_KEY",
    "PUSH_ENDPOINT": "HIBIRA_PUSH_ENDPOINT",
}

DEFAULTS: dict[str, Any] = {
    "HOST": "ws.hibira.io",
    # Send broadcasts made inside a transaction only after it commits, so a
    # browser never fetches a row that was rolled back or isn't visible yet.
    "ON_COMMIT": True,
    # A broadcast larger than the app's event size limit (Hibira answers
    # 413): "refresh" tells the pages to reload instead, "log" logs and drops
    # it, "raise" raises hibira.PayloadTooLarge.
    "OVERSIZE": "refresh",
    # Called by POST /hibira/auth for your own private- and presence-
    # channels: a callable or dotted path, taking (request, channel_name).
    "AUTHORIZE_CHANNEL": None,
    # Returns the push user ID for GET /hibira/push/token: a callable or
    # dotted path taking (request). Defaults to request.user.pk.
    "PUSH_USER_ID": None,
    # Extra keyword arguments for hibira.Client (timeout, ...).
    "CLIENT_OPTIONS": {},
    # False turns every broadcast and trigger into a no-op (handy for
    # management commands and data migrations). None means "on when the
    # credentials are set".
    "ENABLED": None,
}

FALSE = {"false", "0", "no", "off"}


@dataclass(frozen=True)
class Settings:
    app_id: str | None
    key: str | None
    secret: str | None
    host: str
    port: int
    use_tls: bool
    push_instance_id: str | None
    push_secret_key: str | None
    push_endpoint: str | None
    on_commit: bool
    oversize: str
    authorize_channel: Callable[..., Any] | None
    push_user_id: Callable[..., Any] | None
    client_options: dict[str, Any]
    enabled: bool | None

    @property
    def configured(self) -> bool:
        """True when the app ID, key and secret are all set."""
        return all([self.app_id, self.key, self.secret])

    @property
    def push_configured(self) -> bool:
        return bool(self.push_instance_id and self.push_secret_key)

    @property
    def active(self) -> bool:
        """Whether broadcasts are sent right now."""
        if self.enabled is None:
            return self.configured
        return bool(self.enabled)

    @property
    def missing(self) -> list[str]:
        """Environment variable names of the connection settings still blank."""
        values = {"HIBIRA_APP_ID": self.app_id, "HIBIRA_APP_KEY": self.key, "HIBIRA_APP_SECRET": self.secret}
        return [name for name, value in values.items() if not value]


def _raw(name: str, user: dict[str, Any]) -> Any:
    if user.get(name) not in (None, ""):
        return user[name]
    env = ENV.get(name)
    if env and os.environ.get(env):
        return os.environ[env]
    return DEFAULTS.get(name)


def _callable(value: Any) -> Callable[..., Any] | None:
    if value is None or callable(value):
        return value
    return import_string(value)


def _blank(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


def get_settings() -> Settings:
    """Reads the HIBIRA setting and the environment, every call.

    Reading on each call (rather than caching) keeps override_settings and
    monkeypatched environment variables working in tests.
    """
    user = dict(getattr(django_settings, "HIBIRA", {}) or {})
    unknown = set(user) - set(ENV) - set(DEFAULTS)
    if unknown:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(f"Unknown HIBIRA setting(s): {', '.join(sorted(unknown))}")

    use_tls_raw = _raw("USE_TLS", user)
    use_tls = True if use_tls_raw is None else str(use_tls_raw).lower() not in FALSE
    port_raw = _raw("PORT", user)
    port = int(port_raw) if port_raw not in (None, "") else (443 if use_tls else 80)
    oversize = str(_raw("OVERSIZE", user))
    if oversize not in {"refresh", "log", "raise"}:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured('HIBIRA["OVERSIZE"] must be "refresh", "log" or "raise"')

    return Settings(
        app_id=_blank(_raw("APP_ID", user)),
        key=_blank(_raw("KEY", user)),
        secret=_blank(_raw("SECRET", user)),
        host=str(_raw("HOST", user)),
        port=port,
        use_tls=use_tls,
        push_instance_id=_blank(_raw("PUSH_INSTANCE_ID", user)),
        push_secret_key=_blank(_raw("PUSH_SECRET_KEY", user)),
        push_endpoint=_blank(_raw("PUSH_ENDPOINT", user)),
        on_commit=bool(_raw("ON_COMMIT", user)),
        oversize=oversize,
        authorize_channel=_callable(_raw("AUTHORIZE_CHANNEL", user)),
        push_user_id=_callable(_raw("PUSH_USER_ID", user)),
        client_options=dict(_raw("CLIENT_OPTIONS", user) or {}),
        enabled=_raw("ENABLED", user),
    )
