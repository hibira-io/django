import pytest

import django_hibira
from django_hibira.testing import capture_broadcasts
from tests.liveapp.models import Message, Notice, Room

pytestmark = pytest.mark.django_db(transaction=True)


def test_create_appends_update_replaces_delete_removes():
    room = Room.objects.create(name="lobby")
    with capture_broadcasts() as sent:
        message = Message.objects.create(room=room, body="hello")
        message.body = "edited"
        message.save()
        pk = message.pk
        message.delete()

    stream = f"liveapp.room:{room.pk}"
    assert [s.stream for s in sent] == [stream] * 3
    assert [s.action for s in sent] == ["append", "replace", "remove"]
    assert sent[0].target == "messages"
    assert sent[0].html.strip() == f'<li id="message_{pk}">hello</li>'
    assert sent[1].target == f"message_{pk}"
    assert "edited" in sent[1].html
    assert sent[2].target == f"message_{pk}"
    assert sent[2].html is None


def test_refresh_mode_and_model_stream():
    with capture_broadcasts() as sent:
        Notice.objects.create(text="hi")
    assert sent[0].stream == "liveapp.notice"
    assert sent[0].action == "refresh"


def test_cascade_delete_does_not_crash():
    room = Room.objects.create(name="lobby")
    with capture_broadcasts() as sent:
        Message.objects.create(room=room, body="a")
        room.delete()
    assert [s.action for s in sent] == ["append", "remove"]


def test_raw_saves_are_ignored():
    from django.db.models.signals import post_save

    room = Room.objects.create(name="lobby")
    message = Message(room=room, body="fixture", pk=99)
    with capture_broadcasts() as sent:
        post_save.send(sender=Message, instance=message, created=True, raw=True)
    assert sent == []


def test_rejects_bad_options():
    with pytest.raises(ValueError):
        django_hibira.broadcasts(insert="middle")
    with pytest.raises(ValueError):
        django_hibira.broadcasts(on=("explode",))
