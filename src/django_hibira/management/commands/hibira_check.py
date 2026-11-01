from __future__ import annotations

from typing import Any

import hibira
from django.core.management.base import BaseCommand, CommandError
from django.urls import NoReverseMatch, reverse

from django_hibira.client import get_client
from django_hibira.conf import get_settings


class Command(BaseCommand):
    help = "Checks the Hibira settings and that the credentials work."

    def handle(self, *args: Any, **options: Any) -> None:
        s = get_settings()
        ok = True

        if not s.configured:
            raise CommandError(f"Missing {', '.join(s.missing)} (environment or the HIBIRA setting)")
        self.stdout.write(f"ok    App {s.app_id} on {s.host}:{s.port}")
        try:
            get_client().channels()
            self.stdout.write("ok    Credentials accepted by the REST API")
        except hibira.AuthenticationError:
            ok = False
            self.stdout.write("fail  The app key or secret was refused. Copy them again from your app page on hibira.io/portal.")
        except hibira.HibiraError as e:
            ok = False
            self.stdout.write(f"fail  Could not reach {s.host}: {e}")

        try:
            self.stdout.write(f"ok    Browser endpoints at {reverse('hibira:stream_auth').rsplit('streams/', 1)[0]}")
        except NoReverseMatch:
            ok = False
            self.stdout.write('fail  Add path("hibira/", include("django_hibira.urls")) to your root URLconf')

        if s.enabled is False:
            self.stdout.write("info  Broadcasts are off (HIBIRA['ENABLED'] = False)")
        self.stdout.write(
            f"ok    Channel auth via {getattr(s.authorize_channel, '__qualname__', s.authorize_channel)}"
            if s.authorize_channel else
            "info  No HIBIRA['AUTHORIZE_CHANNEL']: only streams can be subscribed to"
        )
        self.stdout.write(
            "ok    Push notifications set up" if s.push_configured else
            "info  Push notifications off (set HIBIRA_PUSH_INSTANCE_ID and HIBIRA_PUSH_SECRET_KEY)"
        )
        if not ok:
            raise CommandError("Hibira check failed")
