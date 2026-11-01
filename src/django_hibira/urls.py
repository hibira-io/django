from django.urls import path

from . import views

app_name = "hibira"

urlpatterns = [
    path("streams/auth", views.stream_auth, name="stream_auth"),
    path("auth", views.channel_auth, name="channel_auth"),
    path("webhooks", views.webhooks, name="webhooks"),
    path("push/token", views.push_token, name="push_token"),
]
