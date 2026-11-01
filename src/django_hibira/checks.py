from __future__ import annotations

from typing import Any

from django.core.checks import Tags, Warning, register
from django.urls import NoReverseMatch, reverse

from .conf import get_settings


@register(Tags.compatibility)
def check_settings(app_configs: Any = None, **kwargs: Any) -> list[Warning]:
    errors = []
    s = get_settings()
    if s.enabled is not False and not s.configured:
        errors.append(Warning(
            f"Hibira is not configured, so nothing is broadcast: set {', '.join(s.missing)}.",
            hint="Copy them from your app page on https://hibira.io/portal, or set HIBIRA['ENABLED'] = False.",
            id="django_hibira.W001",
        ))
    try:
        reverse("hibira:stream_auth")
    except NoReverseMatch:
        errors.append(Warning(
            "The Hibira URLs are not included, so browsers can't subscribe to streams.",
            hint='Add path("hibira/", include("django_hibira.urls")) to your root URLconf.',
            id="django_hibira.W002",
        ))
    return errors
