def authorize(request, channel):
    if not request.user.is_authenticated:
        return False
    if channel.startswith("presence-"):
        return {"user_id": request.user.pk, "user_info": {"name": request.user.username}}
    return channel == f"private-user.{request.user.pk}"
