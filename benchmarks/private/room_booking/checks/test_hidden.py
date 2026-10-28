import uuid
from datetime import date, timedelta


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


def test_missing_partial_or_unknown_identity_is_403(client, actor, uid):
    """[safety] Missing, partial or unknown-role identity headers are exactly 403 on every route and change nothing."""
    day, who = _day(), uid("e")
    bid = _book(client, actor, who, "room-a", day, "17:00", "18:00").json()["id"]
    body = {"room_id": "room-b", "title": "x", "start_at": f"{day}T09:00:00", "end_at": f"{day}T10:00:00"}
    for headers in ({}, {"x-actor-id": who}, {"x-actor-role": "employee"}, actor(who, "visitor")):
        assert client.post("/bookings", json=body, headers=headers).status_code == 403, headers
        assert client.get("/bookings", headers=headers).status_code == 403, headers
        assert client.get(f"/bookings/{bid}", headers=headers).status_code == 403, headers
        assert client.delete(f"/bookings/{bid}", headers=headers).status_code == 403, headers
    assert client.get(f"/bookings/{bid}", headers=actor(who, "employee")).status_code == 200
    assert _book(client, actor, uid("e"), "room-b", day, "09:00", "10:00").status_code == 201


def test_unknown_booking_is_404(client, actor, uid):
    """[functional] Reading or cancelling an unknown booking id is 404 (while the routes exist)."""
    assert _book(client, actor, uid("e"), "room-a", _day(), "09:00", "10:00").status_code == 201
    assert client.get("/bookings/nope", headers=actor(uid("e"), "employee")).status_code == 404
    assert client.delete("/bookings/nope", headers=actor(uid("e"), "employee")).status_code == 404


def test_rejected_bookings_do_not_reserve_the_slot(client, actor, uid):
    """[safety] A booking rejected with 409 or 422 leaves no trace: the time it asked for stays bookable."""
    day = _day()
    assert _book(client, actor, uid("e"), "room-c", day, "09:00", "10:00").status_code == 201
    assert _book(client, actor, uid("e"), "room-c", day, "09:30", "10:30").status_code == 409
    assert _book(client, actor, uid("e"), "room-c", day, "10:00", "11:00").status_code == 201
    assert _book(client, actor, uid("e"), "room-c", day, "12:00", "16:01").status_code == 422
    assert _book(client, actor, uid("e"), "room-c", day, "12:00", "13:00").status_code == 201


def test_overlap_is_decided_by_date_and_time_not_time_of_day(client, actor, uid):
    """[safety] The same clock time on another date does not conflict; a booking across midnight blocks the next morning."""
    first, second = _day(), _day()
    while second == first:
        second = _day()
    assert _book(client, actor, uid("e"), "room-a", first, "09:00", "10:00").status_code == 201
    assert _book(client, actor, uid("e"), "room-a", second, "09:00", "10:00").status_code == 201
    late = _day()
    nxt = (date.fromisoformat(late) + timedelta(days=1)).isoformat()
    body = {"room_id": "room-b", "title": "Late", "start_at": f"{late}T23:00:00", "end_at": f"{nxt}T01:00:00"}
    assert client.post("/bookings", json=body, headers=actor(uid("e"), "employee")).status_code == 201
    assert _book(client, actor, uid("e"), "room-b", nxt, "00:30", "01:30").status_code == 409
    assert _book(client, actor, uid("e"), "room-b", nxt, "01:00", "02:00").status_code == 201


def test_response_fields_match_the_interface(client, actor, uid):
    """[functional] Create, read and list carry id, room_id, booked_by, title, start_at and end_at; an unfiltered list has every room."""
    who, day = uid("e"), _day()
    fields = {"id", "room_id", "booked_by", "title", "start_at", "end_at"}
    a = _book(client, actor, who, "room-a", day, "09:00", "10:00", title="Alpha")
    b = _book(client, actor, who, "room-b", day, "09:00", "10:00")
    assert a.status_code == 201 and fields <= set(a.json())
    assert a.json()["room_id"] == "room-a" and a.json()["title"] == "Alpha"
    read = client.get(f"/bookings/{a.json()['id']}", headers=actor(who, "employee"))
    assert read.status_code == 200 and fields <= set(read.json())
    listed = client.get("/bookings", headers=actor(who, "employee")).json()
    ids = [item["id"] for item in listed]
    assert a.json()["id"] in ids and b.json()["id"] in ids and all(fields <= set(item) for item in listed)


def test_empty_title_missing_fields_and_bad_datetimes_are_422(client, actor, uid):
    """[safety] An empty title, a missing required field or a malformed datetime is rejected with 422 and books nothing."""
    day, headers = _day(), actor(uid("e"), "employee")
    ok = {"room_id": "room-a", "title": "x", "start_at": f"{day}T09:00:00", "end_at": f"{day}T10:00:00"}
    assert client.post("/bookings", json={**ok, "title": ""}, headers=headers).status_code == 422
    for field in ok:
        body = {key: value for key, value in ok.items() if key != field}
        assert client.post("/bookings", json=body, headers=headers).status_code == 422, field
    assert client.post("/bookings", json={**ok, "start_at": "not-a-date"}, headers=headers).status_code == 422
    assert client.post("/bookings", json={**ok, "end_at": "tomorrow"}, headers=headers).status_code == 422
    assert client.post("/bookings", json=ok, headers=headers).status_code == 201
