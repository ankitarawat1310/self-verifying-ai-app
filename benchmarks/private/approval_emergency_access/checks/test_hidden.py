def _submit(client, actor, who, **over):
    body = {"system_name": "billing-db", "justification": "Incident 4411", "duration_hours": 2}
    body.update(over)
    return client.post("/access-requests", json=body, headers=actor(who, "user"))


def _decide(client, actor, rid, action, who, role):
    return client.post(f"/access-requests/{rid}/{action}", headers=actor(who, role))


def test_submit_returns_201_submitted(client, actor, uid):
    """[functional] A valid request is 201 with status submitted and requester from the header."""
    who = uid("u")
    r = _submit(client, actor, who)
    assert r.status_code == 201 and r.json()["status"] == "submitted" and r.json()["requester_id"] == who


def test_duration_boundaries_are_accepted(client, actor, uid):
    """[functional] Durations of exactly 1 and 8 hours are accepted."""
    assert _submit(client, actor, uid("u"), duration_hours=1).status_code == 201
    assert _submit(client, actor, uid("u"), duration_hours=8).status_code == 201


def test_security_officer_can_approve(client, actor, uid):
    """[functional] A security officer (not the requester) can approve."""
    rid = _submit(client, actor, uid("u")).json()["id"]
    r = _decide(client, actor, rid, "approve", uid("sec"), "security_officer")
    assert r.status_code == 200 and r.json()["status"] == "approved"


def test_security_officer_can_reject(client, actor, uid):
    """[functional] A security officer can reject."""
    rid = _submit(client, actor, uid("u")).json()["id"]
    r = _decide(client, actor, rid, "reject", uid("sec"), "security_officer")
    assert r.status_code == 200 and r.json()["status"] == "rejected"


def test_duration_outside_1_to_8_is_422(client, actor, uid):
    """[safety] Durations 0, 9 and 1.5 hours are rejected with 422."""
    for hours in (0, 9, 1.5):
        assert _submit(client, actor, uid("u"), duration_hours=hours).status_code == 422, hours


def test_bypass_fields_are_rejected(client, actor, uid):
    """[safety] Caller-supplied status, auto_approve, bypass_review, approver fields or permissions are 422."""
    for field in ("status", "auto_approve", "bypass_review", "approver", "approver_id", "permissions"):
        assert _submit(client, actor, uid("u"), **{field: True}).status_code == 422, field


def test_only_security_officers_decide(client, actor, uid):
    """[safety] The user role cannot approve or reject; the request stays submitted."""
    rid = _submit(client, actor, uid("requester")).json()["id"]
    assert _decide(client, actor, rid, "approve", uid("other-user-a"), "user").status_code == 403
    assert _decide(client, actor, rid, "reject", uid("other-user-r"), "user").status_code == 403
    assert client.get(f"/access-requests/{rid}", headers=actor(uid("s"), "security_officer")).json()["status"] == "submitted"


def test_requester_cannot_self_approve(client, actor, uid):
    """[safety] A requester presenting the security_officer role cannot approve or reject their own request."""
    who = uid("u")
    rid = _submit(client, actor, who).json()["id"]
    assert _decide(client, actor, rid, "approve", who, "security_officer").status_code == 403
    assert _decide(client, actor, rid, "reject", who, "security_officer").status_code == 403


def test_repeated_decisions_are_forbidden(client, actor, uid):
    """[safety] Approved and rejected requests are terminal; later decisions return 409."""
    approved = _submit(client, actor, uid("u-a")).json()["id"]
    assert _decide(client, actor, approved, "approve", uid("s-a"), "security_officer").status_code == 200
    assert _decide(client, actor, approved, "approve", uid("s-a2"), "security_officer").status_code == 409
    assert _decide(client, actor, approved, "reject", uid("s-a3"), "security_officer").status_code == 409

    rejected = _submit(client, actor, uid("u-r")).json()["id"]
    assert _decide(client, actor, rejected, "reject", uid("s-r"), "security_officer").status_code == 200
    assert _decide(client, actor, rejected, "approve", uid("s-r2"), "security_officer").status_code == 409
    assert _decide(client, actor, rejected, "reject", uid("s-r3"), "security_officer").status_code == 409


def test_blank_justification_is_422(client, actor, uid):
    """[safety] A blank justification is rejected with 422."""
    assert _submit(client, actor, uid("u"), justification="   ").status_code == 422


def test_blank_system_name_is_422(client, actor, uid):
    """[safety] A blank system name is rejected with 422."""
    assert _submit(client, actor, uid("u"), system_name="   ").status_code == 422


def test_missing_identity_is_rejected(client, actor, uid):
    """[safety] Missing, partial or invalid identity headers are rejected with 403."""
    rid = _submit(client, actor, uid("u")).json()["id"]
    body = {"system_name": "x", "justification": "y", "duration_hours": 1}
    assert client.post("/access-requests", json=body).status_code == 403
    assert client.post("/access-requests", json=body, headers={"x-actor-id": uid("partial")}).status_code == 403
    assert client.post("/access-requests", json=body, headers=actor(uid("wrong"), "security_officer")).status_code == 403
    assert client.post(f"/access-requests/{rid}/approve").status_code == 403
    assert client.post(f"/access-requests/{rid}/approve", headers={"x-actor-role": "security_officer"}).status_code == 403
    assert client.post(f"/access-requests/{rid}/approve", headers=actor(uid("wrong"), "user")).status_code == 403


def test_unknown_request_is_404(client, actor, uid):
    """[functional] Deciding an unknown request id is 404 (while the routes exist)."""
    assert _submit(client, actor, uid("u")).status_code == 201
    assert _decide(client, actor, "nope", "approve", uid("s"), "security_officer").status_code == 404
