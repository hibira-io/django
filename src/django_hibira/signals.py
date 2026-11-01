from __future__ import annotations

from typing import Any, Callable

from django.dispatch import Signal

#: Sent once per verified webhook event, with keyword arguments ``name``
#: ("channel_occupied", "member_added", ...), ``event`` (the event dict) and
#: ``time_ms``. ``on_webhook`` is a shortcut for one event name.
webhook_received = Signal()


def on_webhook(*names: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Runs the decorated function for the named webhook events (all of them
    when no name is given). It receives the event dict::

        @on_webhook("channel_vacated")
        def room_emptied(event):
            Room.objects.filter(channel=event["channel"]).update(live=False)
    """

    def decorate(func: Callable[..., Any]) -> Callable[..., Any]:
        def receiver(sender: Any, name: str, event: dict[str, Any], **kwargs: Any) -> None:
            if not names or name in names:
                func(event)

        receiver.__wrapped__ = func  # type: ignore[attr-defined]
        func._hibira_receiver = receiver  # type: ignore[attr-defined]
        webhook_received.connect(receiver, weak=False, dispatch_uid=f"{func.__module__}.{func.__qualname__}")
        return func

    return decorate
