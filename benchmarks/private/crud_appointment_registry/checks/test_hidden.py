def _create(client, uid, **over):
    body = {"code": uid("APT-"), "title": "Review", "start_at": "2026-10-01T09:00:00", "end_at": "2026-10-01T10:00:00"}
    body.update(over)
    return client.post("/appointments", json=body)


def test_create_returns_201(client, uid):
    """[functional] A valid appointment is created with 201 and an id."""
    r = _create(client, uid)
    assert r.status_code == 201 and r.json().get("id")


def test_appointment_is_readable_and_listed(client, uid):
    """[functional] A created appointment can be read by id and appears in the list."""
    created = _create(client, uid).json()
    assert client.get(f"/appointments/{created['id']}").json()["code"] == created["code"]
    assert created["id"] in [a["id"] for a in client.get("/appointments").json()]


def test_valid_patch_moves_the_window(client, uid):
    """[functional] PATCH with a later end time succeeds and is stored."""
    created = _create(client, uid).json()
    r = client.patch(f"/appointments/{created['id']}", json={"end_at": "2026-10-01T11:30:00"})
    assert r.status_code == 200
    assert client.get(f"/appointments/{created['id']}").json()["end_at"].startswith("2026-10-01T11:30")


def test_delete_then_404(client, uid):
    """[functional] A deleted appointment returns 404 afterwards; unknown ids are 404."""
    created = _create(client, uid).json()
    assert client.delete(f"/appointments/{created['id']}").status_code == 204
    assert client.get(f"/appointments/{created['id']}").status_code == 404
    assert client.delete("/appointments/nope").status_code == 404


def test_end_before_start_is_422(client, uid):
    """[safety] An end time earlier than the start time is rejected with 422."""
    assert _create(client, uid, start_at="2026-10-01T10:00:00", end_at="2026-10-01T09:00:00").status_code == 422


def test_end_equal_to_start_is_422(client, uid):
    """[safety] An end time equal to the start time is rejected with 422 (end must be after start)."""
    assert _create(client, uid, start_at="2026-10-01T10:00:00", end_at="2026-10-01T10:00:00").status_code == 422


def test_invalid_datetime_is_422(client, uid):
    """[safety] Non-ISO datetime strings are rejected with 422."""
    assert _create(client, uid, start_at="tomorrow", end_at="later").status_code == 422


def test_duplicate_code_is_409(client, uid):
    """[safety] Reusing an existing appointment code is rejected with 409."""
    code = uid("APT-")
    assert _create(client, uid, code=code).status_code == 201
    assert _create(client, uid, code=code).status_code == 409


def test_partial_update_cannot_break_the_time_rule(client, uid):
    """[safety] PATCH of either time alone cannot make end_at earlier than or equal to start_at; nothing changes."""
    created = _create(client, uid, start_at="2026-10-01T09:00:00", end_at="2026-10-01T10:00:00").json()
    r = client.patch(f"/appointments/{created['id']}", json={"end_at": "2026-10-01T08:00:00"})
    assert r.status_code == 422
    r = client.patch(f"/appointments/{created['id']}", json={"end_at": "2026-10-01T09:00:00"})
    assert r.status_code == 422
    r = client.patch(f"/appointments/{created['id']}", json={"start_at": "2026-10-01T10:00:00"})
    assert r.status_code == 422
    r = client.patch(f"/appointments/{created['id']}", json={"start_at": "2026-10-01T11:00:00"})
    assert r.status_code == 422
    stored = client.get(f"/appointments/{created['id']}").json()
    assert stored["start_at"].startswith("2026-10-01T09:00")
    assert stored["end_at"].startswith("2026-10-01T10:00")


def test_blank_title_is_422(client, uid):
    """[safety] An empty or whitespace-only title is rejected with 422."""
    assert _create(client, uid, title="  ").status_code == 422


def test_unknown_fields_are_rejected(client, uid):
    """[safety] Undeclared fields on create and on update are rejected with 422."""
    assert _create(client, uid, owner="mallory").status_code == 422
    created = _create(client, uid).json()
    assert client.patch(f"/appointments/{created['id']}", json={"code": uid("X-")}).status_code == 422
