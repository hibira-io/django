from django.db import models

from django_hibira import broadcasts


class Room(models.Model):
    name = models.CharField(max_length=100)


@broadcasts(to="room", target="messages")
class Message(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="messages")
    body = models.TextField()


@broadcasts(refresh=True)
class Notice(models.Model):
    text = models.CharField(max_length=100)
