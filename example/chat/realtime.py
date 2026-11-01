def authorize(request, channel):
    """Anyone with a name in their session may join a room's presence
    channel. Return a dict for presence channels, True for private ones."""
    name = request.session.get("name")
    if not name or not channel.startswith("presence-room."):
        return False
    return {"user_id": request.session.session_key, "user_info": {"name": name}}
