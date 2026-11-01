import hibira
import pytest


class FakeClient:
    """Records trigger calls; can be told to fail."""

    def __init__(self):
        self.triggers = []
        self.fail_with = None

    def trigger(self, channels, event, data, socket_id=None):
        if self.fail_with is not None:
            error, self.fail_with = self.fail_with, None
            raise error
        self.triggers.append({"channels": channels, "event": event, "data": data, "socket_id": socket_id})
        return {}


@pytest.fixture
def fake_client(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr("django_hibira.streams.get_client", lambda: client)
    return client


@pytest.fixture
def too_large():
    return hibira.PayloadTooLarge(413, "Payload Too Large", None)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fails any test that would send a real request to Hibira."""
    calls = []
    monkeypatch.setattr(hibira.Client, "trigger", lambda self, *a, **kw: calls.append(a))
    yield
    assert calls == [], f"unexpected real Hibira requests: {calls}"
