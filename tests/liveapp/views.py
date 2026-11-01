from django.shortcuts import get_object_or_404, render

from .models import Room


def room(request, pk):
    room = get_object_or_404(Room, pk=pk)
    return render(request, "liveapp/room.html", {"room": room})
