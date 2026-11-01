import re

import pytest
from django.template import Context, Template
from django.test import RequestFactory

from django_hibira import streams
from tests.liveapp.models import Message, Room

pytestmark = pytest.mark.django_db


def render(source, **context):
    return Template("{% load hibira %}" + source).render(Context(context))


def test_hibira_stream_renders_signed_element():
    room = Room.objects.create(name="a")
    html = render("{% hibira_stream room 'typing' id='live' %}", room=room)
    name = f"liveapp.room:{room.pk}:typing"
    channel = re.search(r'channel="([^"]+)"', html).group(1)
    signed = re.search(r'signed-stream="([^"]+)"', html).group(1)
    assert channel == streams.channel_name(name)
    assert streams.unsign_stream(signed) == name
    assert ' id="live"' in html


def test_dom_id_and_stream_name_tags():
    room = Room.objects.create(name="a")
    message = Message.objects.create(room=room, body="x")
    assert render("{% dom_id message %}", message=message) == f"message_{message.pk}"
    assert render("{% dom_id message 'edit' %}", message=message) == f"edit_message_{message.pk}"
    assert render("{% stream_name room %}", room=room) == f"liveapp.room:{room.pk}"


def test_hibira_scripts_never_includes_the_secret():
    request = RequestFactory().get("/")
    html = Template("{% load hibira %}{% hibira_scripts %}").render(Context({"request": request}))
    assert '<meta name="hibira-key" content="key_1">' in html
    assert '<meta name="hibira-host" content="hibira.test">' in html
    assert '<meta name="hibira-port" content="443">' in html
    assert 'content="/hibira/streams/auth"' in html
    assert 'name="hibira-csrf-token"' in html
    assert "/static/django_hibira/vendor/pusher.min.js" in html
    assert "/static/django_hibira/hibira.js" in html
    assert "secret_1" not in html


def test_hibira_scripts_without_pusher():
    html = render("{% hibira_scripts pusher=False %}")
    assert "pusher.min.js" not in html


def test_room_page(client):
    room = Room.objects.create(name="a")
    Message.objects.create(room=room, body="first")
    html = client.get(f"/rooms/{room.pk}/").content.decode()
    assert "<hibira-stream" in html and "first" in html
