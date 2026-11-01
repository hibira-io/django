import hashlib
import logging

import hibira
import pytest
from django.db import transaction
from django.test import override_settings

import django_hibira
from django_hibira import streams
from django_hibira.testing import capture_broadcasts
from tests.liveapp.models import Message, Room

pytestmark = pytest.mark.django_db


def test_stream_name_from_models_and_strings():
    room = Room.objects.create(name="a")
    assert django_hibira.stream_name(room) == f"liveapp.room:{room.pk}"
    assert django_hibira.stream_name(room, "typing") == f"liveapp.room:{room.pk}:typing"
    assert django_hibira.stream_name(Message) == "liveapp.message"
    assert django_hibira.stream_name(["a", None, ("b",)]) == "a:b"
    with pytest.raises(ValueError):
        django_hibira.stream_name(None, "")
    with pytest.raises(ValueError):
        django_hibira.stream_name(Room(name="unsaved"))


def test_channel_name_is_a_private_digest():
    expected = "private-stream-" + hashlib.sha256(b"liveapp.room:1").hexdigest()
    assert django_hibira.channel_name("liveapp.room:1") == expected
    assert len(expected) <= 164


def test_dom_id():
    room = Room.objects.create(name="a")
    assert django_hibira.dom_id(room) == f"room_{room.pk}"
    assert django_hibira.dom_id(room, "edit") == f"edit_room_{room.pk}"
    assert django_hibira.dom_id(Room(name="new")) == "new_room"
    assert django_hibira.dom_id(Room) == "new_room"


def test_signed_stream_round_trip():
    signed = streams.sign_stream("liveapp.room:1")
    assert streams.unsign_stream(signed) == "liveapp.room:1"
    assert streams.unsign_stream(signed + "x") is None
    assert streams.unsign_stream("liveapp.room:2:" + signed.rsplit(":", 1)[1]) is None


def test_broadcast_sends_html_operation(fake_client):
    django_hibira.broadcast_append("feed", target="items", html="<li>1</li>", on_commit=False)
    sent = fake_client.triggers[0]
    assert sent["channels"] == django_hibira.channel_name("feed")
    assert sent["event"] == "html-swap"
    assert sent["data"] == {"action": "append", "target": "items", "html": "<li>1</li>"}


def test_broadcast_renders_template(fake_client):
    room = Room.objects.create(name="a")
    message = Message(room=room, body="<b>hi</b>", pk=7)
    django_hibira.broadcast_replace(room, target=message, template="liveapp/_message.html",
                                    context={"message": message}, on_commit=False)
    data = fake_client.triggers[-1]["data"]
    assert data["target"] == "message_7"
    assert data["html"].strip() == '<li id="message_7">&lt;b&gt;hi&lt;/b&gt;</li>'


def test_remove_and_refresh_carry_no_html(fake_client):
    django_hibira.broadcast_remove("feed", target="item_1", on_commit=False)
    django_hibira.broadcast_refresh("feed", on_commit=False)
    assert fake_client.triggers[0]["data"] == {"action": "remove", "target": "item_1"}
    assert fake_client.triggers[1]["data"] == {"action": "refresh"}


def test_targets_selector_and_socket_id(fake_client):
    django_hibira.broadcast_update("feed", targets=".count", html="3", socket_id="1.2", on_commit=False)
    sent = fake_client.triggers[0]
    assert sent["data"] == {"action": "update", "targets": ".count", "html": "3"}
    assert sent["socket_id"] == "1.2"


def test_validation():
    with pytest.raises(ValueError):
        django_hibira.broadcast("feed", action="explode", target="x")
    with pytest.raises(ValueError):
        django_hibira.broadcast_append("feed", html="x")


@pytest.mark.django_db(transaction=True)
def test_waits_for_commit_and_skips_rollback(fake_client):
    with transaction.atomic():
        django_hibira.broadcast_append("feed", target="items", html="a")
        assert fake_client.triggers == []
    assert len(fake_client.triggers) == 1

    with pytest.raises(RuntimeError):
        with transaction.atomic():
            django_hibira.broadcast_append("feed", target="items", html="b")
            raise RuntimeError
    assert len(fake_client.triggers) == 1


@pytest.mark.django_db(transaction=True)
@override_settings(HIBIRA={"APP_ID": "a", "KEY": "k", "SECRET": "s", "ON_COMMIT": False})
def test_on_commit_setting_off_sends_inside_transaction(fake_client):
    with transaction.atomic():
        django_hibira.broadcast_append("feed", target="items", html="a")
        assert len(fake_client.triggers) == 1


def test_oversize_sends_refresh(fake_client, too_large, caplog):
    fake_client.fail_with = too_large
    with caplog.at_level(logging.WARNING, logger="django_hibira"):
        django_hibira.broadcast_append("feed", target="items", html="x" * 20000, on_commit=False)
    assert fake_client.triggers == [{"channels": django_hibira.channel_name("feed"), "event": "html-swap",
                                     "data": {"action": "refresh"}, "socket_id": None}]
    assert "sent a page refresh instead" in caplog.text


@override_settings(HIBIRA={"APP_ID": "a", "KEY": "k", "SECRET": "s", "OVERSIZE": "log"})
def test_oversize_log_drops(fake_client, too_large, caplog):
    fake_client.fail_with = too_large
    django_hibira.broadcast_append("feed", target="items", html="x", on_commit=False)
    assert fake_client.triggers == []
    assert "dropped" in caplog.text


@override_settings(HIBIRA={"APP_ID": "a", "KEY": "k", "SECRET": "s", "OVERSIZE": "raise"})
def test_oversize_raise(fake_client, too_large):
    fake_client.fail_with = too_large
    with pytest.raises(hibira.PayloadTooLarge):
        django_hibira.broadcast_append("feed", target="items", html="x", on_commit=False)


def test_network_errors_are_logged_not_raised(fake_client, caplog):
    fake_client.fail_with = hibira.HibiraError("connection refused")
    django_hibira.broadcast_append("feed", target="items", html="x", on_commit=False)
    fake_client.fail_with = OSError("network down")
    django_hibira.trigger("private-a", "e", {}, on_commit=False)
    assert caplog.text.count("failed") == 2


@override_settings(HIBIRA={})
def test_nothing_is_sent_without_credentials(fake_client, monkeypatch):
    for name in ("HIBIRA_APP_ID", "HIBIRA_APP_KEY", "HIBIRA_APP_SECRET"):
        monkeypatch.delenv(name, raising=False)
    django_hibira.broadcast_append("feed", target="items", html="x", on_commit=False)
    django_hibira.trigger("private-a", "e", {}, on_commit=False)
    assert fake_client.triggers == []


@override_settings(HIBIRA={"APP_ID": "a", "KEY": "k", "SECRET": "s", "ENABLED": False})
def test_enabled_false_turns_sending_off(fake_client):
    django_hibira.broadcast_append("feed", target="items", html="x", on_commit=False)
    assert fake_client.triggers == []


def test_trigger_plain_event(fake_client):
    django_hibira.trigger(["private-a", "private-b"], "order.paid", {"id": 1}, socket_id="1.1", on_commit=False)
    assert fake_client.triggers == [{"channels": ["private-a", "private-b"], "event": "order.paid",
                                     "data": {"id": 1}, "socket_id": "1.1"}]


def test_capture_records_instead_of_sending(fake_client):
    with capture_broadcasts() as sent:
        django_hibira.broadcast_append("feed", target="items", html="<li>", on_commit=False)
        django_hibira.trigger("private-a", "ping", {"x": 1}, on_commit=False)
    assert fake_client.triggers == []
    assert sent[0].stream == "feed" and sent[0].action == "append" and sent[0].html == "<li>"
    assert sent.for_stream("feed") == [sent[0]]
    assert sent.events("ping")[0].data == {"x": 1}
