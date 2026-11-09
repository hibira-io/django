import base64
import hashlib
import hmac
import json
import time

from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from django_hibira.waiting_room import WaitingRoomMiddleware, verify_pass, waiting_room, waiting_room_url

# Signed by the Hibira server (internal/waitroom NewPass) at 1800000000, ttl 30 min.
SERVER_SECRET = "wr-secret-0123456789"
SERVER_PASS = (
    "eyJ2IjoxLCJhcHAiOiJ3ci1hcHAiLCJyb29tIjoicHJlc2FsZSIsIm4iOjQyLCJ0aWQiOiJkNzlmZTc4OWEzOGI4NjMxYjUiLCJpYXQiOjE4MDAwMDAw"
    "MDAsImV4cCI6MTgwMDAwMTgwMH0.q7Uc_O6XKwNA_LVLQITlgv_YtDi9dIwiRzUUUSsGa08"
)
SERVER_TICKET = (
    "eyJ2IjoxLCJhcHAiOiJ3ci1hcHAiLCJyb29tIjoicHJlc2FsZSIsIm4iOjQyLCJ0aWQiOiJkNzlmZTc4OWEzOGI4NjMxYjUiLCJpYXQiOjE4MDAwMDAw"
    "MDAsImV4cCI6MTgwMDA4NjQwMH0.l-KNMOVwV_xJJCQaQ-JXQKsrj-XlEdsTxG7X4Kp_2ck"
)
NOW = 1800000100

rf = RequestFactory()


def sign(claims, secret="secret_1"):
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    sig = hmac.new(secret.encode(), b"hibira-waitroom-pass." + payload.encode(), hashlib.sha256).digest()
    return payload + "." + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()


def fresh(room="presale"):
    now = int(time.time())
    return sign({"v": 1, "app": "app_1", "room": room, "n": 7, "tid": "t7", "iat": now, "exp": now + 600})


def test_verifies_a_server_pass():
    p = verify_pass(SERVER_PASS, SERVER_SECRET, room="presale", app_id="wr-app", now=NOW)
    assert (p.number, p.ticket_id, p.expires_at) == (42, "d79fe789a38b8631b5", 1800001800)
    assert verify_pass(SERVER_PASS, ["old", SERVER_SECRET], now=NOW), "rotation: any secret"


def test_rejects_forged_expired_foreign_and_tickets():
    assert verify_pass(SERVER_PASS, "wrong", now=NOW) is None
    assert verify_pass(SERVER_PASS, SERVER_SECRET, room="other", now=NOW) is None
    assert verify_pass(SERVER_PASS, SERVER_SECRET, app_id="other", now=NOW) is None
    assert verify_pass(SERVER_PASS, SERVER_SECRET, now=1800001800) is None
    assert verify_pass(SERVER_TICKET, SERVER_SECRET, now=NOW) is None
    assert verify_pass(SERVER_PASS[:-3] + "AAA", SERVER_SECRET, now=NOW) is None
    for bad in ("", None, "a.b.c", "!!.??"):
        assert verify_pass(bad, SERVER_SECRET, now=NOW) is None
    assert verify_pass(sign({"v": 2, "exp": 9e9}), "secret_1") is None


def view(request):
    return HttpResponse(f"in #{request.hibira_pass.number}")


protected = waiting_room("presale")(view)


def test_waiting_room_url_uses_the_configured_host():
    assert waiting_room_url("presale", "https://shop.example.com/drop?id=1") == (
        "https://hibira.test/wait/key_1/presale?return=https%3A%2F%2Fshop.example.com%2Fdrop%3Fid%3D1"
    )


def test_visitor_without_pass_goes_to_the_queue():
    res = protected(rf.get("/drop", {"id": "1"}, secure=True, HTTP_HOST="shop.example.com"))
    assert res.status_code == 302
    assert res["Location"] == waiting_room_url("presale", "https://shop.example.com/drop?id=1")
    assert res["Cache-Control"] == "no-store"
    post = protected(rf.post("/drop", secure=True))
    assert post.status_code == 403
    assert json.loads(post.content)["error"] == "waiting_room"


def test_pass_from_the_queue_becomes_a_cookie():
    token = fresh()
    res = protected(rf.get("/drop", {"id": "1", "hibira_pass": token}, secure=True, HTTP_HOST="shop.example.com"))
    assert res.status_code == 302
    assert res["Location"] == "https://shop.example.com/drop?id=1"
    cookie = res.cookies["hibira_wr_presale"]
    assert cookie.value == token and cookie["httponly"] and cookie["secure"] and cookie["samesite"] == "Lax"
    assert 0 < int(cookie["max-age"]) <= 600

    req = rf.get("/drop", secure=True)
    req.COOKIES["hibira_wr_presale"] = token
    assert protected(req).content == b"in #7"


def test_bad_or_foreign_pass_goes_back_to_the_queue():
    for token in (sign({"v": 1, "app": "app_1", "room": "presale", "exp": 9e9}, "nope"), fresh("other")):
        res = protected(rf.get("/drop", {"hibira_pass": token}, HTTP_HOST="shop.example.com"))
        assert res["Location"].startswith("https://hibira.test/wait/key_1/presale?return=http%3A%2F%2Fshop.example.com%2Fdrop")
        assert "hibira_pass" not in res["Location"]


@override_settings(HIBIRA={"APP_ID": "app_1", "KEY": "key_1", "SECRET": "secret_1", "HOST": "hibira.test",
                           "WAITING_ROOMS": {"/drop/": "presale", "/drop/vip/": "vip"}})
def test_middleware_protects_prefixes():
    mw = WaitingRoomMiddleware(lambda request: HttpResponse("ok"))
    assert mw(rf.get("/")).content == b"ok"
    assert "/wait/key_1/presale?" in mw(rf.get("/drop/a"))["Location"]
    assert "/wait/key_1/vip?" in mw(rf.get("/drop/vip/a"))["Location"]
    req = rf.get("/drop/a")
    req.COOKIES["hibira_wr_presale"] = fresh()
    assert mw(req).content == b"ok"
