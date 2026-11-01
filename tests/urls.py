from django.urls import include, path

from tests.liveapp import views

urlpatterns = [
    path("hibira/", include("django_hibira.urls")),
    path("rooms/<int:pk>/", views.room, name="room"),
]
