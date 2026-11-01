import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import override_settings

from django_hibira.checks import check_settings
from django_hibira.client import get_client
from django_hibira.conf import get_settings


@override_settings(HIBIRA={})
def test_environment_fallback(monkeypatch):
    monkeypatch.setenv("HIBIRA_APP_ID", "env-app")
    monkeypatch.setenv("HIBIRA_APP_KEY", "env-key")
    monkeypatch.setenv("HIBIRA_APP_SECRET", "env-secret")
    monkeypatch.setenv("HIBIRA_USE_TLS", "false")
    s = get_settings()
    assert (s.app_id, s.key, s.secret, s.host, s.port, s.use_tls) == ("env-app", "env-key", "env-secret",
                                                                       "ws.hibira.io", 80, False)
    assert s.active


@override_settings(HIBIRA={"APP_ID": "a", "KEY": "k", "SECRET": "s", "HOST": "localhost", "PORT": "6001"})
def test_client_is_cached_until_settings_change():
    client = get_client()
    assert client is get_client()
    with override_settings(HIBIRA={"APP_ID": "a", "KEY": "k", "SECRET": "s2"}):
        assert get_client() is not client


@override_settings(HIBIRA={"APP_ID": "a", "KEY": "k", "SECRET": "s", "TYPO": 1})
def test_unknown_setting_is_an_error():
    with pytest.raises(ImproperlyConfigured):
        get_settings()


@override_settings(HIBIRA={"APP_ID": "a", "KEY": "k", "SECRET": "s", "OVERSIZE": "explode"})
def test_bad_oversize():
    with pytest.raises(ImproperlyConfigured):
        get_settings()


@override_settings(HIBIRA={})
def test_missing_credentials(monkeypatch):
    for name in ("HIBIRA_APP_ID", "HIBIRA_APP_KEY", "HIBIRA_APP_SECRET"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ImproperlyConfigured, match="HIBIRA_APP_ID"):
        get_client()
    assert [w.id for w in check_settings()] == ["django_hibira.W001"]


def test_system_check_clean():
    assert check_settings() == []


@override_settings(ROOT_URLCONF="tests.urls_without_hibira")
def test_system_check_missing_urls():
    assert [w.id for w in check_settings()] == ["django_hibira.W002"]


def test_hibira_check_command(monkeypatch, capsys):
    class Ok:
        def channels(self):
            return {"channels": {}}

    monkeypatch.setattr("django_hibira.management.commands.hibira_check.get_client", lambda: Ok())
    call_command("hibira_check")
    out = capsys.readouterr().out
    assert "Credentials accepted" in out and "/hibira/" in out
