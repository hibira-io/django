from django.db import models

from django_hibira import broadcasts


class Room(models.Model):
    name = models.CharField(max_length=80)

    def __str__(self):
        return self.name


@broadcasts(to="room", target="messages")
class Message(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="messages")
    author = models.CharField(max_length=40)
    body = models.TextField(max_length=2000)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created"]
