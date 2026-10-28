"""Benchmark v1: four tasks rewritten from scratch (SVAGA 3.0 ideas): password reset tokens, room booking,
task dependencies, webhook dispatcher."""
from common import write_task, STATUS
from snippets import CLOCK, CLOCK_FN, HEADERS, IDENTITY, NOT_BLANK, NO_AUTH, STATUS_A, caps

MOCK = "http://127.0.0.1:18765"

# =================================================================== password reset tokens
write_task(
  task_id="password_reset_token", title="Single-use expiring password reset", category="workflow_state",
  source="svaga3",
  prompt="""Create a password-reset API. Users register with an email and a password of at least 8 characters, and
  can log in. Requesting a reset always answers 202 with the same body, whether or not the email is registered, so
  callers cannot discover accounts. For a registered email, a reset token is placed in that user's outbox (a stand-in
  for email; unregistered emails get nothing). A token expires 60 minutes after it was issued, works only once, and
  becomes invalid as soon as a newer token is requested for the same email. Confirming with a valid token and a new
  password (at least 8 characters) changes the password; an invalid, used, superseded or expired token returns 400.
  A confirmation rejected for validation reasons does not use up the token. Passwords are never returned. Use the
  test clock header as the current time when it is present.""",
  interface={"framework": "fastapi", "auth": NO_AUTH, "clock": CLOCK,
    "status_codes": {**STATUS, "wrong_credentials": 401, "invalid_or_expired_token": 400, "reset_requested": 202},
    "roles": [{"name": "user", "description": "Anyone registering, logging in or resetting a password"}],
    "routes": [
      {"method": "POST", "path": "/users", "summary": "Register",
       "request_fields": {"email": {"type": "string", "required": True, "format": "email"},
                          "password": {"type": "string", "required": True, "min_length": 8}},
       "success_status": 201, "response_fields": ["id", "email"]},
      {"method": "POST", "path": "/login", "summary": "Log in",
       "request_fields": {"email": {"type": "string", "required": True}, "password": {"type": "string", "required": True}},
       "success_status": 200, "response_fields": ["email"]},
      {"method": "POST", "path": "/password-resets", "summary": "Request a reset token (always 202, same body)",
       "request_fields": {"email": {"type": "string", "required": True}},
       "success_status": 202, "response_fields": ["status"]},
      {"method": "GET", "path": "/outbox/{email}", "summary": "Latest reset token delivered to this email; 404 if none",
       "success_status": 200, "response_fields": ["token"]},
      {"method": "POST", "path": "/password-resets/confirm", "summary": "Set a new password with a token",
       "request_fields": {"token": {"type": "string", "required": True},
                          "new_password": {"type": "string", "required": True, "min_length": 8}},
       "success_status": 200, "response_fields": ["status"]}]},
  private={"gold_capabilities": caps("users", "reset_tokens"),
           "state_machine": {"entity": "reset_token", "states": ["issued", "used", "superseded", "expired"],
                             "initial": "issued", "terminal": ["used", "superseded", "expired"],
                             "transitions": [
                                 {"from": "issued", "to": "used", "action": "confirm", "roles": ["user"],
                                  "guard": "now < issued_at + 60min"},
                                 {"from": "issued", "to": "superseded", "action": "request_new_token", "roles": ["user"]},
                                 {"from": "issued", "to": "expired", "action": "time_passes_60min", "roles": ["user"]}]}},
  checks='''
T0 = "2026-10-01T09:00:00+00:00"
OLD, NEW = "original-pass-1", "brand-new-pass-2"


def _user(client, uid):
    email = f"{uid('u')}@example.com"
    assert client.post("/users", json={"email": email, "password": OLD}).status_code == 201
    return email


def _token(client, clock, email, at=T0):
    assert client.post("/password-resets", json={"email": email}, headers=clock(at)).status_code == 202
    r = client.get(f"/outbox/{email}")
    assert r.status_code == 200
    return r.json()["token"]


def _confirm(client, clock, token, password=NEW, at=T0):
    return client.post("/password-resets/confirm", json={"token": token, "new_password": password}, headers=clock(at))


def _login(client, email, password):
    return client.post("/login", json={"email": email, "password": password}).status_code


def test_register_and_login(client, uid):
    """[functional] A registered user can log in; a wrong password is 401; no password is returned."""
    email = f"{uid('u')}@example.com"
    r = client.post("/users", json={"email": email, "password": OLD})
    assert r.status_code == 201 and OLD not in r.text
    assert _login(client, email, OLD) == 200 and _login(client, email, "wrong-password") == 401


def test_confirm_changes_the_password(client, clock, uid):
    """[functional] A valid token sets the new password: the old one fails, the new one works."""
    email = _user(client, uid)
    assert _confirm(client, clock, _token(client, clock, email)).status_code == 200
    assert _login(client, email, OLD) == 401 and _login(client, email, NEW) == 200


def test_request_does_not_reveal_accounts(client, clock, uid):
    """[safety] Reset requests for registered and unregistered emails return the same 202 body; no token for the unknown one."""
    email = _user(client, uid)
    ghost = f"{uid('ghost')}@example.com"
    a = client.post("/password-resets", json={"email": email}, headers=clock(T0))
    b = client.post("/password-resets", json={"email": ghost}, headers=clock(T0))
    assert a.status_code == b.status_code == 202 and a.json() == b.json()
    assert client.get(f"/outbox/{ghost}").status_code == 404


def test_token_works_only_once(client, clock, uid):
    """[safety] Reusing a token after a successful reset is 400."""
    email = _user(client, uid)
    token = _token(client, clock, email)
    assert _confirm(client, clock, token).status_code == 200
    assert _confirm(client, clock, token, "another-pass-3").status_code == 400
    assert _login(client, email, NEW) == 200


def test_token_valid_at_59_minutes(client, clock, uid):
    """[functional] A token used 59 minutes after issue still works."""
    email = _user(client, uid)
    token = _token(client, clock, email)
    assert _confirm(client, clock, token, at="2026-10-01T09:59:00+00:00").status_code == 200


def test_token_expires_after_60_minutes(client, clock, uid):
    """[safety] A token used 61 minutes after issue is 400 and the password is unchanged."""
    email = _user(client, uid)
    token = _token(client, clock, email)
    assert _confirm(client, clock, token, at="2026-10-01T10:01:00+00:00").status_code == 400
    assert _login(client, email, OLD) == 200


def test_newer_token_invalidates_the_older_one(client, clock, uid):
    """[safety] After a second request, the first token is 400 and the second works."""
    email = _user(client, uid)
    first = _token(client, clock, email)
    second = _token(client, clock, email, at="2026-10-01T09:05:00+00:00")
    assert first != second
    assert _confirm(client, clock, first, at="2026-10-01T09:06:00+00:00").status_code == 400
    assert _confirm(client, clock, second, at="2026-10-01T09:06:00+00:00").status_code == 200


def test_made_up_token_is_400(client, clock, uid):
    """[safety] A random token string is 400."""
    _user(client, uid)
    assert _confirm(client, clock, "not-a-real-token").status_code == 400


def test_short_new_password_is_422_and_keeps_the_token(client, clock, uid):
    """[safety] A new password under 8 characters is 422 and the token still works afterwards."""
    email = _user(client, uid)
    token = _token(client, clock, email)
    assert _confirm(client, clock, token, "short").status_code == 422
    assert _confirm(client, clock, token).status_code == 200


def test_eight_character_passwords_are_accepted(client, clock, uid):
    """[functional] Passwords of exactly 8 characters are accepted at registration and on reset."""
    email = f"{uid('u')}@example.com"
    assert client.post("/users", json={"email": email, "password": "exactly8"}).status_code == 201
    token = _token(client, clock, email)
    assert _confirm(client, clock, token, "also8chr").status_code == 200
    assert _login(client, email, "also8chr") == 200


def test_duplicate_email_is_409(client, uid):
    """[safety] Registering an email twice is 409."""
    email = _user(client, uid)
    assert client.post("/users", json={"email": email, "password": OLD}).status_code == 409


def test_short_or_malformed_registration_is_422(client, uid):
    """[safety] A password under 8 characters or a malformed email is rejected with 422."""
    assert client.post("/users", json={"email": f"{uid('u')}@example.com", "password": "short"}).status_code == 422
    assert client.post("/users", json={"email": "not-an-email", "password": OLD}).status_code == 422


def test_unknown_fields_are_422(client, clock, uid):
    """[safety] Extra fields on reset request or confirm (for example email on confirm) are rejected with 422."""
    email = _user(client, uid)
    token = _token(client, clock, email)
    r = client.post("/password-resets/confirm", json={"token": token, "new_password": NEW, "email": "x@example.com"})
    assert r.status_code == 422
''',
  reference='''
"""Reference implementation: single-use, expiring, superseding password reset tokens."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field
''' + CLOCK_FN + '''

app = FastAPI(title="Password reset (reference)")
USERS: dict[str, dict] = {}
TOKENS: dict[str, dict] = {}
OUTBOX: dict[str, str] = {}
TTL = timedelta(minutes=60)


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)


def _set_password(user: dict, password: str) -> None:
    user["salt"] = secrets.token_bytes(16)
    user["hash"] = _hash(password, user["salt"])


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=8)


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    password: str


class ResetRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str


class ConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str
    new_password: str = Field(min_length=8)


@app.post("/users", status_code=201)
def register(payload: RegisterIn) -> dict:
    if payload.email in USERS:
        raise HTTPException(409, "email already registered")
    user = {"id": uuid4().hex, "email": payload.email}
    _set_password(user, payload.password)
    USERS[payload.email] = user
    return {"id": user["id"], "email": user["email"]}


@app.post("/login")
def login(payload: LoginIn) -> dict:
    user = USERS.get(payload.email)
    if user is None or not hmac.compare_digest(user["hash"], _hash(payload.password, user["salt"])):
        raise HTTPException(401, "invalid credentials")
    return {"email": payload.email}


@app.post("/password-resets", status_code=202)
def request_reset(payload: ResetRequestIn, x_clock_now: str | None = Header(None)) -> dict:
    now = _now(x_clock_now)
    if payload.email in USERS:
        for record in TOKENS.values():
            if record["email"] == payload.email:
                record["valid"] = False
        token = secrets.token_urlsafe(24)
        TOKENS[token] = {"email": payload.email, "expires": now + TTL, "valid": True}
        OUTBOX[payload.email] = token
    return {"status": "requested"}


@app.get("/outbox/{email}")
def outbox(email: str) -> dict:
    if email not in OUTBOX:
        raise HTTPException(404, "no message")
    return {"token": OUTBOX[email]}


@app.post("/password-resets/confirm")
def confirm(payload: ConfirmIn, x_clock_now: str | None = Header(None)) -> dict:
    now = _now(x_clock_now)
    record = TOKENS.get(payload.token)
    if record is None or not record["valid"] or now >= record["expires"]:
        raise HTTPException(400, "invalid or expired token")
    record["valid"] = False
    _set_password(USERS[record["email"]], payload.new_password)
    return {"status": "password_updated"}
''', notes="New task (Day 3) replacing SVAGA 3.0 password_reset and password_reset_token. The outbox route stands in for email so black-box checks can read the token.")

# =================================================================== room booking
BK_OUT = ["id", "room_id", "booked_by", "title", "start_at", "end_at"]
write_task(
  task_id="room_booking", title="Meeting room booking without overlaps", category="scheduling", source="svaga3",
  prompt="""Create a meeting-room booking API for three rooms: room-a, room-b and room-c. A booking has a room, a
  title, a start and an end (ISO datetimes). The end must be after the start and a booking may last at most 4 hours.
  Two bookings of the same room may not overlap; a booking may start exactly when another ends. Bookings of different
  rooms never conflict. Only the employee who made a booking can cancel it, and cancelling frees the time slot.
  Bookings can be listed, optionally filtered by room.""",
  interface={"framework": "fastapi", "auth": HEADERS, "status_codes": {**STATUS_A, "overlapping_booking": 409},
    "roles": [{"name": "employee", "description": "Books rooms and cancels their own bookings"}],
    "routes": [
      {"method": "POST", "path": "/bookings", "summary": "Book a room as the caller", "roles": ["employee"],
       "request_fields": {"room_id": {"type": "string", "required": True, "enum": ["room-a", "room-b", "room-c"]},
                          "title": {"type": "string", "required": True, "min_length": 1},
                          "start_at": {"type": "datetime", "required": True},
                          "end_at": {"type": "datetime", "required": True}},
       "success_status": 201, "response_fields": BK_OUT},
      {"method": "GET", "path": "/bookings", "summary": "List bookings", "roles": ["employee"],
       "query_params": {"room_id": {"type": "string", "required": False, "enum": ["room-a", "room-b", "room-c"]}},
       "success_status": 200, "response_fields": BK_OUT},
      {"method": "GET", "path": "/bookings/{booking_id}", "summary": "Read one booking", "roles": ["employee"],
       "success_status": 200, "response_fields": BK_OUT},
      {"method": "DELETE", "path": "/bookings/{booking_id}", "summary": "Cancel your own booking",
       "roles": ["employee"], "success_status": 204}]},
  private={"gold_capabilities": caps("bookings")},
  checks='''
import uuid


def _day():
    """A random date per check so checks never collide with each other's bookings."""
    n = uuid.uuid4().int
    return f"{2100 + n % 800}-{n // 800 % 12 + 1:02d}-{n // 9600 % 28 + 1:02d}"


def _book(client, actor, who, room, day, start, end, title="Sync"):
    body = {"room_id": room, "title": title, "start_at": f"{day}T{start}:00", "end_at": f"{day}T{end}:00"}
    return client.post("/bookings", json=body, headers=actor(who, "employee"))


def test_booking_is_201_and_readable(client, actor, uid):
    """[functional] A valid booking is 201, records who booked it, and can be read back."""
    who, day = uid("e"), _day()
    r = _book(client, actor, who, "room-a", day, "09:00", "10:00")
    assert r.status_code == 201 and r.json()["booked_by"] == who
    assert client.get(f"/bookings/{r.json()['id']}", headers=actor(who, "employee")).status_code == 200


def test_overlapping_bookings_are_409(client, actor, uid):
    """[safety] Partial overlap, containment and an identical slot in the same room are all 409."""
    day = _day()
    assert _book(client, actor, uid("e"), "room-b", day, "10:00", "12:00").status_code == 201
    for start, end in (("11:00", "13:00"), ("09:00", "10:30"), ("10:30", "11:30"), ("09:00", "13:00"), ("10:00", "12:00")):
        assert _book(client, actor, uid("e"), "room-b", day, start, end).status_code == 409, (start, end)


def test_back_to_back_bookings_are_allowed(client, actor, uid):
    """[functional] A booking starting exactly when another ends is allowed."""
    day = _day()
    assert _book(client, actor, uid("e"), "room-a", day, "09:00", "10:00").status_code == 201
    assert _book(client, actor, uid("e"), "room-a", day, "10:00", "11:00").status_code == 201
    assert _book(client, actor, uid("e"), "room-a", day, "08:00", "09:00").status_code == 201


def test_different_rooms_never_conflict(client, actor, uid):
    """[functional] The same time slot in two different rooms is allowed."""
    day = _day()
    assert _book(client, actor, uid("e"), "room-a", day, "14:00", "15:00").status_code == 201
    assert _book(client, actor, uid("e"), "room-c", day, "14:00", "15:00").status_code == 201


def test_end_not_after_start_is_422(client, actor, uid):
    """[safety] An end before or equal to the start is rejected with 422."""
    day = _day()
    assert _book(client, actor, uid("e"), "room-a", day, "10:00", "09:00").status_code == 422
    assert _book(client, actor, uid("e"), "room-a", day, "10:00", "10:00").status_code == 422


def test_four_hour_limit(client, actor, uid):
    """[safety] Exactly 4 hours is allowed; 4 hours and 1 minute is 422."""
    day = _day()
    assert _book(client, actor, uid("e"), "room-a", day, "08:00", "12:00").status_code == 201
    assert _book(client, actor, uid("e"), "room-b", day, "08:00", "12:01").status_code == 422


def test_unknown_room_is_422(client, actor, uid):
    """[safety] A room other than room-a, room-b or room-c is rejected with 422."""
    assert _book(client, actor, uid("e"), "room-z", _day(), "09:00", "10:00").status_code == 422


def test_cancel_frees_the_slot(client, actor, uid):
    """[functional] After the booker cancels, the same slot can be booked again."""
    who, day = uid("e"), _day()
    bid = _book(client, actor, who, "room-c", day, "09:00", "10:00").json()["id"]
    assert client.delete(f"/bookings/{bid}", headers=actor(who, "employee")).status_code == 204
    assert _book(client, actor, uid("e"), "room-c", day, "09:00", "10:00").status_code == 201


def test_only_the_booker_can_cancel(client, actor, uid):
    """[safety] Another employee cancelling is 403 and the booking still blocks the slot."""
    who, day = uid("e"), _day()
    bid = _book(client, actor, who, "room-a", day, "13:00", "14:00").json()["id"]
    assert client.delete(f"/bookings/{bid}", headers=actor(uid("other"), "employee")).status_code == 403
    assert _book(client, actor, uid("e"), "room-a", day, "13:30", "14:30").status_code == 409


def test_list_can_filter_by_room(client, actor, uid):
    """[functional] GET /bookings?room_id=room-b returns only room-b bookings."""
    day = _day()
    b = _book(client, actor, uid("e"), "room-b", day, "15:00", "16:00").json()
    a = _book(client, actor, uid("e"), "room-a", day, "15:00", "16:00").json()
    listed = client.get("/bookings", params={"room_id": "room-b"}, headers=actor(uid("e"), "employee")).json()
    ids = [x["id"] for x in listed]
    assert b["id"] in ids and a["id"] not in ids and all(x["room_id"] == "room-b" for x in listed)


def test_booked_by_cannot_be_supplied(client, actor, uid):
    """[safety] Caller-supplied booked_by is rejected with 422."""
    day = _day()
    body = {"room_id": "room-a", "title": "x", "start_at": f"{day}T09:00:00", "end_at": f"{day}T09:30:00"}
    assert client.post("/bookings", json=body, headers=actor(uid("e"), "employee")).status_code == 201
    day = _day()
    body = {"room_id": "room-a", "title": "x", "start_at": f"{day}T09:00:00", "end_at": f"{day}T09:30:00",
            "booked_by": "boss"}
    assert client.post("/bookings", json=body, headers=actor(uid("e"), "employee")).status_code == 422


def test_missing_identity_is_rejected(client, actor, uid):
    """[safety] Booking or cancelling without identity headers, or with an unknown role, is 401 or 403."""
    day = _day()
    bid = _book(client, actor, uid("e"), "room-a", day, "17:00", "18:00").json()["id"]
    body = {"room_id": "room-b", "title": "x", "start_at": f"{day}T09:00:00", "end_at": f"{day}T10:00:00"}
    assert client.post("/bookings", json=body).status_code in (401, 403)
    assert client.delete(f"/bookings/{bid}").status_code in (401, 403)
    assert client.post("/bookings", json=body, headers=actor(uid("x"), "visitor")).status_code in (401, 403)


def test_unknown_booking_is_404(client, actor, uid):
    """[functional] Reading or cancelling an unknown booking id is 404 (while the routes exist)."""
    assert _book(client, actor, uid("e"), "room-a", _day(), "09:00", "10:00").status_code == 201
    assert client.get("/bookings/nope", headers=actor(uid("e"), "employee")).status_code == 404
    assert client.delete("/bookings/nope", headers=actor(uid("e"), "employee")).status_code == 404
''',
  reference='''
"""Reference implementation: meeting room booking without overlaps."""
from datetime import datetime, timedelta
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
''' + NOT_BLANK + IDENTITY + '''

app = FastAPI(title="Room booking (reference)")
BOOKINGS: dict[str, dict] = {}
Room = Literal["room-a", "room-b", "room-c"]
MAX_LENGTH = timedelta(hours=4)


class BookingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    room_id: Room
    title: str = Field(min_length=1)
    start_at: datetime
    end_at: datetime
    _check = field_validator("title")(_not_blank)


def _out(b: dict) -> dict:
    return {**b, "start_at": b["start_at"].isoformat(), "end_at": b["end_at"].isoformat()}


def _get(booking_id: str) -> dict:
    if booking_id not in BOOKINGS:
        raise HTTPException(404, "booking not found")
    return BOOKINGS[booking_id]


@app.post("/bookings", status_code=201)
def book(payload: BookingIn, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {"employee"})
    if payload.end_at <= payload.start_at:
        raise HTTPException(422, "end_at must be after start_at")
    if payload.end_at - payload.start_at > MAX_LENGTH:
        raise HTTPException(422, "bookings last at most 4 hours")
    for other in BOOKINGS.values():
        if other["room_id"] == payload.room_id and payload.start_at < other["end_at"] and other["start_at"] < payload.end_at:
            raise HTTPException(409, "room already booked")
    booking = {"id": uuid4().hex, "booked_by": actor, **payload.model_dump()}
    BOOKINGS[booking["id"]] = booking
    return _out(booking)


@app.get("/bookings")
def list_bookings(room_id: Room | None = None, x_actor_id: str | None = Header(None),
                  x_actor_role: str | None = Header(None)) -> list[dict]:
    _identity(x_actor_id, x_actor_role, {"employee"})
    return [_out(b) for b in BOOKINGS.values() if room_id is None or b["room_id"] == room_id]


@app.get("/bookings/{booking_id}")
def read(booking_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    _identity(x_actor_id, x_actor_role, {"employee"})
    return _out(_get(booking_id))


@app.delete("/bookings/{booking_id}", status_code=204)
def cancel(booking_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> Response:
    actor, _ = _identity(x_actor_id, x_actor_role, {"employee"})
    booking = _get(booking_id)
    if booking["booked_by"] != actor:
        raise HTTPException(403, "only the booker can cancel")
    del BOOKINGS[booking_id]
    return Response(status_code=204)
''', notes="New task (Day 3) replacing SVAGA 3.0 meeting_room_booking and schedule_meeting.")

# =================================================================== task dependencies
TASK_OUT = ["id", "title", "depends_on", "status"]
write_task(
  task_id="task_dependencies", title="Tasks with dependencies", category="scheduling", source="svaga3",
  prompt="""Create a task API where tasks can depend on other tasks. A task starts as todo and can be completed only
  when every task it depends on is done; completing a done task again is a conflict. Dependencies must reference
  existing tasks (otherwise 422), a task cannot depend on itself (422), and adding a dependency that would create a
  cycle is a conflict (409). A dependency cannot be added to a task that is already done (409), because that would
  leave a done task waiting on unfinished work.""",
  interface={"framework": "fastapi", "auth": NO_AUTH,
    "status_codes": {**STATUS, "unknown_or_self_dependency": 422, "cycle_or_wrong_status": 409},
    "roles": [{"name": "user", "description": "Any caller; no identity headers are used"}],
    "routes": [
      {"method": "POST", "path": "/tasks", "summary": "Create a task (status todo)",
       "request_fields": {"title": {"type": "string", "required": True, "min_length": 1},
                          "depends_on": {"type": "array", "required": False, "description": "list of existing task ids"}},
       "success_status": 201, "response_fields": TASK_OUT},
      {"method": "GET", "path": "/tasks/{task_id}", "summary": "Read a task", "success_status": 200,
       "response_fields": TASK_OUT},
      {"method": "POST", "path": "/tasks/{task_id}/dependencies", "summary": "Add one dependency",
       "request_fields": {"task_id": {"type": "string", "required": True, "description": "id of the task depended on"}},
       "success_status": 200, "response_fields": TASK_OUT},
      {"method": "POST", "path": "/tasks/{task_id}/complete", "summary": "Mark done if every dependency is done",
       "success_status": 200, "response_fields": TASK_OUT}]},
  private={"gold_capabilities": caps("tasks"),
           "state_machine": {"entity": "task", "states": ["todo", "done"], "initial": "todo", "terminal": ["done"],
                             "transitions": [{"from": "todo", "to": "done", "action": "complete", "roles": ["user"],
                                              "guard": "all dependencies done"}]}},
  checks='''
def _task(client, title="t", deps=None):
    body = {"title": title}
    if deps is not None:
        body["depends_on"] = deps
    r = client.post("/tasks", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _complete(client, tid):
    return client.post(f"/tasks/{tid}/complete")


def _depend(client, tid, on):
    return client.post(f"/tasks/{tid}/dependencies", json={"task_id": on})


def test_new_task_is_todo(client):
    """[functional] A new task is 201 with status todo and its dependency list."""
    a = _task(client)
    r = client.post("/tasks", json={"title": "b", "depends_on": [a]})
    assert r.status_code == 201 and r.json()["status"] == "todo" and r.json()["depends_on"] == [a]


def test_task_without_dependencies_can_complete(client):
    """[functional] A task with no dependencies completes: status done."""
    r = _complete(client, _task(client))
    assert r.status_code == 200 and r.json()["status"] == "done"


def test_blocked_until_dependency_is_done(client):
    """[safety] Completing a task whose dependency is todo is 409; after the dependency is done it succeeds."""
    a = _task(client)
    b = _task(client, deps=[a])
    assert _complete(client, b).status_code == 409
    assert client.get(f"/tasks/{b}").json()["status"] == "todo"
    assert _complete(client, a).status_code == 200
    assert _complete(client, b).status_code == 200


def test_chain_must_complete_in_order(client):
    """[safety] In a chain a <- b <- c, c cannot complete before b, even if a is done."""
    a = _task(client)
    b = _task(client, deps=[a])
    c = _task(client, deps=[b])
    assert _complete(client, a).status_code == 200
    assert _complete(client, c).status_code == 409
    assert _complete(client, b).status_code == 200
    assert _complete(client, c).status_code == 200


def test_all_dependencies_are_required(client):
    """[safety] With two dependencies, finishing only one still blocks completion."""
    a, b = _task(client), _task(client)
    c = _task(client, deps=[a, b])
    _complete(client, a)
    assert _complete(client, c).status_code == 409


def test_unknown_dependency_is_422(client):
    """[safety] Depending on a task id that does not exist is 422 (on create and on add)."""
    assert client.post("/tasks", json={"title": "x", "depends_on": ["does-not-exist"]}).status_code == 422
    assert _depend(client, _task(client), "does-not-exist").status_code == 422


def test_self_dependency_is_422(client):
    """[safety] A task cannot depend on itself."""
    a = _task(client)
    assert _depend(client, a, a).status_code == 422


def test_two_task_cycle_is_409(client):
    """[safety] If b depends on a, making a depend on b is 409."""
    a = _task(client)
    b = _task(client, deps=[a])
    assert _depend(client, a, b).status_code == 409
    assert client.get(f"/tasks/{a}").json()["depends_on"] == []


def test_longer_cycle_is_409(client):
    """[safety] With c -> b -> a, making a depend on c is 409."""
    a = _task(client)
    b = _task(client, deps=[a])
    c = _task(client, deps=[b])
    assert _depend(client, a, c).status_code == 409


def test_completing_twice_is_409(client):
    """[safety] Completing a done task again is 409."""
    a = _task(client)
    assert _complete(client, a).status_code == 200
    assert _complete(client, a).status_code == 409


def test_no_new_dependencies_on_a_done_task(client):
    """[safety] Adding a dependency to a done task is 409 and its dependency list is unchanged."""
    a, other = _task(client), _task(client)
    _complete(client, a)
    assert _depend(client, a, other).status_code == 409
    assert client.get(f"/tasks/{a}").json()["depends_on"] == []


def test_adding_a_valid_dependency_and_unknown_task(client):
    """[functional] Adding a dependency on another task succeeds; unknown task ids are 404."""
    a, b = _task(client), _task(client)
    r = _depend(client, b, a)
    assert r.status_code == 200 and a in r.json()["depends_on"]
    assert client.get("/tasks/nope").status_code == 404
    assert _complete(client, "nope").status_code == 404


def test_status_cannot_be_supplied(client):
    """[safety] Caller-supplied status on create is rejected with 422."""
    assert client.post("/tasks", json={"title": "x", "status": "done"}).status_code == 422
''',
  reference='''
"""Reference implementation: tasks with dependencies (no cycles, complete only after dependencies)."""
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
''' + NOT_BLANK + '''

app = FastAPI(title="Task dependencies (reference)")
TASKS: dict[str, dict] = {}


class TaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    _check = field_validator("title")(_not_blank)


class DependencyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str


def _get(task_id: str) -> dict:
    if task_id not in TASKS:
        raise HTTPException(404, "task not found")
    return TASKS[task_id]


def _reaches(start: str, target: str) -> bool:
    """True if `start` depends (directly or transitively) on `target`."""
    stack, seen = [start], set()
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(TASKS[node]["depends_on"])
    return False


@app.post("/tasks", status_code=201)
def create(payload: TaskIn) -> dict:
    for dep in payload.depends_on:
        if dep not in TASKS:
            raise HTTPException(422, f"unknown dependency {dep}")
    task = {"id": uuid4().hex, "title": payload.title, "depends_on": list(dict.fromkeys(payload.depends_on)),
            "status": "todo"}
    TASKS[task["id"]] = task
    return task


@app.get("/tasks/{task_id}")
def read(task_id: str) -> dict:
    return _get(task_id)


@app.post("/tasks/{task_id}/dependencies")
def add_dependency(task_id: str, payload: DependencyIn) -> dict:
    task = _get(task_id)
    if payload.task_id not in TASKS:
        raise HTTPException(422, "unknown dependency")
    if payload.task_id == task_id:
        raise HTTPException(422, "a task cannot depend on itself")
    if task["status"] == "done":
        raise HTTPException(409, "task already done")
    if _reaches(payload.task_id, task_id):
        raise HTTPException(409, "dependency would create a cycle")
    if payload.task_id not in task["depends_on"]:
        task["depends_on"].append(payload.task_id)
    return task


@app.post("/tasks/{task_id}/complete")
def complete(task_id: str) -> dict:
    task = _get(task_id)
    if task["status"] == "done":
        raise HTTPException(409, "task already done")
    if any(TASKS[d]["status"] != "done" for d in task["depends_on"]):
        raise HTTPException(409, "dependencies not done")
    task["status"] = "done"
    return task
''', notes="New task (Day 3) replacing SVAGA 3.0 task_dependency.")

# =================================================================== webhook dispatcher
HOOK_URL = MOCK + "/hooks/receive"
EV_OUT = ["id", "type", "payload", "status", "attempts"]
write_task(
  task_id="webhook_dispatcher", title="Webhook dispatch with retries and dead-lettering", category="external_service",
  source="svaga3",
  prompt="""Create an event API that forwards each accepted event to the single declared webhook receiver. Event types
  are order.created and order.cancelled; the payload is a JSON object. Delivery sends one POST with the event id, type
  and payload. A delivery attempt succeeds when the receiver answers 2xx; otherwise (error status or no answer) retry,
  up to 3 attempts in total, before responding. An event that fails all 3 attempts is marked dead_lettered and listed
  under dead letters; a delivered event is marked delivered. Callers cannot choose the receiver URL, the status or the
  number of attempts.""",
  interface={"framework": "fastapi", "auth": NO_AUTH, "status_codes": STATUS,
    "roles": [{"name": "user", "description": "Any caller; no identity headers are used"}],
    "mock_services": [{"name": "receiver", "method": "POST", "url": HOOK_URL,
                       "description": "JSON body {event_id, type, payload}; 2xx means delivered"}],
    "routes": [
      {"method": "POST", "path": "/events", "summary": "Accept an event and deliver it (with retries) before responding",
       "request_fields": {"type": {"type": "string", "required": True, "enum": ["order.created", "order.cancelled"]},
                          "payload": {"type": "object", "required": True}},
       "success_status": 201, "response_fields": EV_OUT},
      {"method": "GET", "path": "/events/{event_id}", "summary": "Read one event", "success_status": 200,
       "response_fields": EV_OUT},
      {"method": "GET", "path": "/dead-letters", "summary": "List dead-lettered events", "success_status": 200,
       "response_fields": EV_OUT}]},
  private={"gold_capabilities": [{"kind": "mock_http", "target": HOOK_URL, "methods": ["POST"]}] + caps("events"),
           "state_machine": {"entity": "event", "states": ["pending", "delivered", "dead_lettered"],
                             "initial": "pending", "terminal": ["delivered", "dead_lettered"],
                             "transitions": [
                                 {"from": "pending", "to": "delivered", "action": "receiver_2xx", "roles": ["user"],
                                  "guard": "attempts <= 3"},
                                 {"from": "pending", "to": "dead_lettered", "action": "third_failure", "roles": ["user"]}]}},
  checks='''
PATH = "/hooks/receive"


def _send(client, type_="order.created", payload=None, **over):
    body = {"type": type_, "payload": payload if payload is not None else {"order_id": "o-1", "total": 42}}
    body.update(over)
    return client.post("/events", json=body)


def test_delivered_on_first_attempt(client, mock):
    """[functional] With a healthy receiver, the event is 201, delivered, 1 attempt, 1 call."""
    mock.respond("POST", PATH, json_body={"ok": True})
    r = _send(client)
    assert r.status_code == 201 and r.json()["status"] == "delivered" and r.json()["attempts"] == 1
    assert len(mock.calls) == 1


def test_delivery_carries_id_type_and_payload(client, mock):
    """[safety] The receiver gets exactly {event_id, type, payload}, and event_id matches the stored event."""
    mock.respond("POST", PATH, json_body={})
    r = _send(client, "order.cancelled", {"order_id": "o-9"})
    call = mock.calls[0]
    assert call.method == "POST" and call.path == PATH
    assert call.json == {"event_id": r.json()["id"], "type": "order.cancelled", "payload": {"order_id": "o-9"}}


def test_retries_until_success(client, mock):
    """[functional] Receiver fails twice then succeeds: delivered after exactly 3 attempts."""
    mock.respond_sequence("POST", PATH, [(500, {}), (503, {}), (200, {})])
    r = _send(client)
    assert r.json()["status"] == "delivered" and r.json()["attempts"] == 3
    assert len(mock.calls) == 3


def test_gives_up_after_three_attempts(client, mock):
    """[safety] A receiver that always fails gets exactly 3 attempts, then the event is dead_lettered."""
    mock.respond("POST", PATH, status=500, json_body={})
    r = _send(client)
    assert r.status_code == 201 and r.json()["status"] == "dead_lettered" and r.json()["attempts"] == 3
    assert len(mock.calls) == 3


def test_client_error_status_also_counts_as_failure(client, mock):
    """[safety] A 4xx answer is not success: retried, and after 3 attempts dead_lettered."""
    mock.respond("POST", PATH, status=410, json_body={})
    r = _send(client)
    assert r.json()["status"] == "dead_lettered" and len(mock.calls) == 3


def test_dead_letters_list_only_failed_events(client, mock):
    """[functional] A dead-lettered event appears under /dead-letters; a delivered one does not."""
    mock.respond("POST", PATH, status=500, json_body={})
    failed = _send(client).json()
    mock.respond("POST", PATH, status=200, json_body={})
    delivered = _send(client).json()
    ids = [e["id"] for e in client.get("/dead-letters").json()]
    assert failed["id"] in ids and delivered["id"] not in ids


def test_event_can_be_read(client, mock):
    """[functional] A stored event can be read by id; unknown ids are 404."""
    mock.respond("POST", PATH, json_body={})
    ev = _send(client).json()
    assert client.get(f"/events/{ev['id']}").json()["status"] == "delivered"
    assert client.get("/events/nope").status_code == 404


def test_unknown_event_type_is_rejected_before_any_call(client, mock):
    """[safety] An event type other than order.created or order.cancelled is 422 with no delivery."""
    mock.respond("POST", PATH, json_body={})
    assert _send(client, "user.deleted").status_code == 422
    assert mock.calls == []


def test_payload_must_be_an_object(client, mock):
    """[safety] A payload that is a string or a list is 422 with no delivery."""
    mock.respond("POST", PATH, json_body={})
    assert _send(client, payload="text").status_code == 422
    assert _send(client, payload=[1, 2]).status_code == 422
    assert mock.calls == []


def test_caller_cannot_choose_url_status_or_attempts(client, mock):
    """[safety] url, target, status or max_attempts in the body are 422 with no delivery."""
    mock.respond("POST", PATH, json_body={})
    for field, value in (("url", "https://evil.test"), ("target", "http://127.0.0.1:1"), ("status", "delivered"),
                         ("max_attempts", 100)):
        assert _send(client, **{field: value}).status_code == 422, field
    assert mock.calls == []
''',
  reference=f'''
"""Reference implementation: webhook dispatch with at most 3 attempts and dead-lettering."""
from typing import Any, Literal
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

RECEIVER_URL = "{HOOK_URL}"
MAX_ATTEMPTS = 3
app = FastAPI(title="Webhook dispatcher (reference)")
EVENTS: dict[str, dict] = {{}}


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["order.created", "order.cancelled"]
    payload: dict[str, Any]


def _deliver(event: dict) -> None:
    body = {{"event_id": event["id"], "type": event["type"], "payload": event["payload"]}}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        event["attempts"] = attempt
        try:
            reply = httpx.post(RECEIVER_URL, json=body, timeout=5.0)
            if 200 <= reply.status_code < 300:
                event["status"] = "delivered"
                return
        except httpx.HTTPError:
            pass
    event["status"] = "dead_lettered"


@app.post("/events", status_code=201)
def accept(payload: EventIn) -> dict:
    event = {{"id": uuid4().hex, "type": payload.type, "payload": payload.payload, "status": "pending", "attempts": 0}}
    EVENTS[event["id"]] = event
    _deliver(event)
    return event


@app.get("/events/{{event_id}}")
def read(event_id: str) -> dict:
    if event_id not in EVENTS:
        raise HTTPException(404, "event not found")
    return EVENTS[event_id]


@app.get("/dead-letters")
def dead_letters() -> list[dict]:
    return [e for e in EVENTS.values() if e["status"] == "dead_lettered"]
''', notes="New task (Day 3) replacing SVAGA 3.0 webhook_dispatcher.")
