import random

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

import django_hibira

from .models import Message, Room

NAMES = ["Aiko", "Bao", "Chen", "Dana", "Emi", "Farah", "Goro", "Hana", "Ivan", "Jun", "Kai", "Lin"]


def lobby(request):
    room, _ = Room.objects.get_or_create(pk=1, defaults={"name": "General"})
    return redirect("room", pk=room.pk)


def room(request, pk):
    room = get_object_or_404(Room, pk=pk)
    if not request.session.get("name"):
        request.session["name"] = random.choice(NAMES)
        request.session.save()
    return render(request, "chat/room.html", {"room": room, "messages": room.messages.all()[:200]})


@require_POST
def send(request, pk):
    room = get_object_or_404(Room, pk=pk)
    body = request.POST.get("body", "").strip()
    if body:
        Message.objects.create(room=room, author=request.session.get("name", "guest"), body=body[:2000])
        django_hibira.broadcast_update(room, target="count", html=str(room.messages.count()))
    return HttpResponse(status=204)
