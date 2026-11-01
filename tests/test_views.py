import hashlib
import hmac
import json

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings

from django_hibira import on_webhook, streams, webhook_received

pytestmark = pytest.mark.django_db

SECRET = "secret_1"


def sign(text):
    return hmac.new(SECRET.encode(), text.encode(), hashlib.sha256).hexdigest()


def test_stream_auth_signs_valid_stream(client):
    name = "liveapp.room:1"
    channel = streams.channel_name(name)
    response = client.post("/hibira/streams/auth", {
        "socket_id": "123.456", "channel_name": channel, "signed_stream_name": streams.sign_stream(name),
    })
    assert response.status_code == 200
    assert response.json() == {"auth": "key_1:" + sign(f"123.456:{channel}")}


def test_stream_auth_refuses_mismatched_or_forged(client):
    name = "liveapp.room:1"
    other = streams.channel_name("liveapp.room:2")
    assert client.post("/hibira/streams/auth", {
        "socket_id": "1.1", "channel_name": other, "signed_stream_name": streams.sign_stream(name),
    }).status_code == 403
    assert client.post("/hibira/streams/auth", {
        "socket_id": "1.1", "channel_name": streams.channel_name(name), "signed_stream_name": name + ":forged",
    }).status_code == 403
    assert client.get("/hibira/streams/auth").status_code == 405


def test_stream_auth_needs_no_csrf_token():
    csrf_client = Client(enforce_csrf_checks=True)
    name = "x"
    response = csrf_client.post("/hibira/streams/auth", {
        "socket_id": "1.1", "channel_name": streams.channel_name(name), "signed_stream_name": streams.sign_stream(name),
    })
    assert response.status_code == 200


def test_channel_auth_private_and_presence(client):
    user = User.objects.create_user("aiko", password="pw")
    assert client.post("/hibira/auth", {"socket_id": "1.1", "channel_name": f"private-user.{user.pk}"}).status_code == 403

    client.force_login(user)
    response = client.post("/hibira/auth", {"socket_id": "1.1", "channel_name": f"private-user.{user.pk}"})
    assert response.status_code == 200
    assert response.json()["auth"] == "key_1:" + sign(f"1.1:private-user.{user.pk}")

    assert client.post("/hibira/auth", {"socket_id": "1.1", "channel_name": "private-user.999"}).status_code == 403

    response = client.post("/hibira/auth", {"socket_id": "1.1", "channel_name": "presence-room.1"})
    body = response.json()
    assert json.loads(body["channel_data"]) == {"user_id": str(user.pk), "user_info": {"name": "aiko"}}
    assert body["auth"] == "key_1:" + sign(f"1.1:presence-room.1:{body['channel_data']}")


def test_channel_auth_refuses_streams_and_public(client):
    user = User.objects.create_user("aiko")
    client.force_login(user)
    assert client.post("/hibira/auth", {"socket_id": "1.1", "channel_name": streams.channel_name("x")}).status_code == 403
    assert client.post("/hibira/auth", {"socket_id": "1.1", "channel_name": "public"}).status_code == 403


def test_channel_auth_is_csrf_protected():
    csrf_client = Client(enforce_csrf_checks=True)
    user = User.objects.create_user("aiko")
    csrf_client.force_login(user)
    response = csrf_client.post("/hibira/auth", {"socket_id": "1.1", "channel_name": f"private-user.{user.pk}"})
    assert response.status_code == 403


@override_settings(HIBIRA={"APP_ID": "a", "KEY": "key_1", "SECRET": SECRET})
def test_channel_auth_refuses_without_authorize_setting(client):
    user = User.objects.create_user("aiko")
    client.force_login(user)
    assert client.post("/hibira/auth", {"socket_id": "1.1", "channel_name": f"private-user.{user.pk}"}).status_code == 403


def post_webhook(client, body, signature=None, header="HTTP_X_PUSHER_SIGNATURE", key="key_1"):
    return client.post("/hibira/webhooks", body, content_type="application/json",
                       HTTP_X_PUSHER_KEY=key, **{header: signature if signature is not None else sign(body)})


def test_webhooks_send_signals(client):
    received = []

    def receiver(sender, name, event, time_ms, **kwargs):
        received.append((name, event["channel"], time_ms))

    webhook_received.connect(receiver)
    try:
        body = json.dumps({"time_ms": 5, "events": [
            {"name": "channel_occupied", "channel": "presence-a"},
            {"name": "member_added", "channel": "presence-a", "user_id": "1"},
            "junk",
        ]})
        assert post_webhook(client, body).status_code == 200
    finally:
        webhook_received.disconnect(receiver)
    assert received == [("channel_occupied", "presence-a", 5), ("member_added", "presence-a", 5)]


def test_on_webhook_filters_by_name(client):
    vacated = []

    @on_webhook("channel_vacated")
    def handler(event):
        vacated.append(event["channel"])

    try:
        body = json.dumps({"time_ms": 1, "events": [
            {"name": "channel_occupied", "channel": "a"}, {"name": "channel_vacated", "channel": "b"},
        ]})
        assert post_webhook(client, body).status_code == 200
    finally:
        webhook_received.disconnect(handler._hibira_receiver)
    assert vacated == ["b"]


def test_webhooks_refuse_bad_signature_and_key(client):
    body = json.dumps({"events": []})
    assert post_webhook(client, body, signature="0" * 64).status_code == 401
    assert post_webhook(client, body, key="other").status_code == 401
    assert client.post("/hibira/webhooks", body, content_type="application/json").status_code == 401


def test_webhooks_accept_previous_secret_header(client):
    body = json.dumps({"events": []})
    response = client.post("/hibira/webhooks", body, content_type="application/json", HTTP_X_PUSHER_KEY="key_1",
                           HTTP_X_PUSHER_SIGNATURE="0" * 64, HTTP_X_HIBIRA_PREVIOUS_SIGNATURE=sign(body))
    assert response.status_code == 200


def test_push_token_off_without_push_settings(client):
    assert client.get("/hibira/push/token?user_id=1").status_code == 404


@override_settings(HIBIRA={"APP_ID": "a", "KEY": "k", "SECRET": "s", "PUSH_INSTANCE_ID": "i", "PUSH_SECRET_KEY": "p"})
def test_push_token_for_signed_in_user_only(client, monkeypatch):
    class Push:
        def push_token(self, user_id):
            return {"token": f"t-{user_id}"}

    monkeypatch.setattr("django_hibira.views.get_client", lambda: Push())
    user = User.objects.create_user("aiko")
    assert client.get(f"/hibira/push/token?user_id={user.pk}").status_code == 401
    client.force_login(user)
    assert client.get("/hibira/push/token?user_id=999").status_code == 401
    response = client.get(f"/hibira/push/token?user_id={user.pk}")
    assert response.json() == {"token": f"t-{user.pk}"}


def test_socket_id_helper(rf):
    from django_hibira import socket_id

    assert socket_id(rf.get("/", HTTP_X_HIBIRA_SOCKET_ID="1.2")) == "1.2"
    assert socket_id(rf.post("/", {"hibira_socket_id": "3.4"})) == "3.4"
    assert socket_id(rf.get("/")) is None
