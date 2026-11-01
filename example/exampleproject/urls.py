from django.urls import include, path

from chat import views

urlpatterns = [
    path("hibira/", include("django_hibira.urls")),
    path("", views.lobby, name="lobby"),
    path("rooms/<int:pk>/", views.room, name="room"),
    path("rooms/<int:pk>/messages", views.send, name="send"),
]
