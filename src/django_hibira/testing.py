"""Test helpers.

Inside ``capture_broadcasts()``, broadcasts and triggers are recorded instead
of sent, whether or not Hibira credentials are set::

    from django_hibira.testing import capture_broadcasts

    def test_new_message_is_appended(room):
        with capture_broadcasts() as sent:
            Message.objects.create(room=room, body="hi")
        assert sent[0].action == "append"
        assert sent[0].stream == f"chat.room:{room.pk}"
        assert "hi" in sent[0].html

Broadcasts wait for the transaction to commit. Django's ``TestCase`` never
commits, so wrap the code in ``self.captureOnCommitCallbacks(execute=True)``,
use ``TransactionTestCase``, or with pytest-django mark the test
``@pytest.mark.django_db(transaction=True)`` or use the
``django_capture_on_commit_callbacks`` fixture.
"""

from __future__ import annotations

import contextlib
import threading
from dataclasses import dataclass
from typing import Any, Iterator

_local = threading.local()


@dataclass
class Sent:
    channels: Any
    event: str
    data: Any
    socket_id: str | None = None
    stream: str | None = None

    @property
    def action(self) -> str | None:
        return self.data.get("action") if isinstance(self.data, dict) else None

    @property
    def target(self) -> str | None:
        return self.data.get("target") if isinstance(self.data, dict) else None

    @property
    def html(self) -> str | None:
        return self.data.get("html") if isinstance(self.data, dict) else None


class Recorder(list):
    """A list of Sent, with filters."""

    def for_stream(self, *streamables: Any) -> list[Sent]:
        from .streams import stream_name

        name = stream_name(*streamables)
        return [s for s in self if s.stream == name]

    def events(self, name: str) -> list[Sent]:
        return [s for s in self if s.event == name]


@contextlib.contextmanager
def capture_broadcasts() -> Iterator[Recorder]:
    stack = getattr(_local, "stack", None)
    if stack is None:
        stack = _local.stack = []
    recorder = Recorder()
    stack.append(recorder)
    try:
        yield recorder
    finally:
        stack.remove(recorder)


def record(channels: Any, event: str, data: Any, socket_id: str | None, stream: str | None = None) -> bool:
    """Records a send in the innermost capture, if any. Returns True when
    recorded (the caller then sends nothing)."""
    stack = getattr(_local, "stack", None)
    if not stack:
        return False
    stack[-1].append(Sent(channels, event, data, socket_id, stream))
    return True
