import hashlib
import hmac

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.template import Context, Template
from django.test import RequestFactory, override_settings

from django_hibira.livechat import identity, user_hash

pytestmark = pytest.mark.django_db

BASE = {"APP_ID": "app_1", "KEY": "key_1", "SECRET": "secret_1", "HOST": "hibira.test"}


def render(user, source="{% hibira_live_chat %}"):
    request = RequestFactory().get("/")
    request.user = user
    return Template("{% load hibira %}" + source).render(Context({"request": request}))


def test_user_hash():
    assert user_hash("lcid_s", 42) == hmac.new(b"lcid_s", b"42", hashlib.sha256).hexdigest()
    with pytest.raises(ValueError):
        user_hash("", 1)


def test_nothing_without_a_workspace():
    assert render(AnonymousUser()) == ""


@override_settings(HIBIRA={**BASE, "LIVECHAT_WORKSPACE": "ws_1"})
def test_anonymous_visitor_and_options():
    html = render(AnonymousUser(), "{% hibira_live_chat color='#0a7' lang='ja' launcher=False %}")
    assert html == (
        '<script src="https://chat.hibira.io/w/v1.js" data-workspace="ws_1" data-color="#0a7"'
        ' data-lang="ja" data-launcher="none" async></script>'
    )


@override_settings(HIBIRA={**BASE, "LIVECHAT_WORKSPACE": "ws_1"})
def test_signed_in_user_without_a_secret_is_not_verified():
    user = User.objects.create_user("ann", "ann@example.com", "x")
    assert "data-user-id" not in render(user)


@override_settings(HIBIRA={**BASE, "LIVECHAT_WORKSPACE": "ws_1", "LIVECHAT_IDENTITY_SECRET": "lcid_s"})
def test_signed_in_user_is_verified_and_escaped():
    user = User.objects.create_user("ann", "ann@example.com", "x", first_name='Ann "A"', last_name="<Lee>")
    html = render(user)
    want = hmac.new(b"lcid_s", str(user.pk).encode(), hashlib.sha256).hexdigest()
    assert f'data-user-id="{user.pk}" data-user-hash="{want}"' in html
    assert 'data-user-name="Ann &quot;A&quot; &lt;Lee&gt;"' in html
    assert 'data-user-email="ann@example.com"' in html
    assert identity(user) == {"id": str(user.pk), "hash": want, "name": 'Ann "A" <Lee>', "email": "ann@example.com"}
    assert identity(AnonymousUser()) is None


def test_env_settings(monkeypatch):
    monkeypatch.setenv("HIBIRA_LIVECHAT_WORKSPACE", "ws_env")
    assert 'data-workspace="ws_env"' in render(AnonymousUser())
