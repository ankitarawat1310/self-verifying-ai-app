def _submit(client, actor, who="emp", **over):
    body = {"reason": "Family trip", "start_date": "2026-11-02", "end_date": "2026-11-06"}
    body.update(over)
    return client.post("/leave-requests", json=body, headers=actor(who, "employee"))


def test_submit_returns_201_submitted_with_requester_from_header(client, actor, uid):
    """[functional] An employee's submission is 201, status submitted, requester taken from the identity header."""
    who = uid("emp")
    r = _submit(client, actor, who)
    assert r.status_code == 201
    assert r.json()["status"] == "submitted" and r.json()["requester_id"] == who


def test_request_can_be_read(client, actor, uid):
    """[functional] A submitted request can be read back by id."""
    created = _submit(client, actor, uid("emp")).json()
    r = client.get(f"/leave-requests/{created['id']}", headers=actor(uid("mgr"), "manager"))
    assert r.status_code == 200 and r.json()["id"] == created["id"]


def test_manager_can_approve(client, actor, uid):
    """[functional] Another user with the manager role can approve a submitted request."""
    created = _submit(client, actor, uid("emp")).json()
    r = client.post(f"/leave-requests/{created['id']}/approve", headers=actor(uid("mgr"), "manager"))
    assert r.status_code == 200 and r.json()["status"] == "approved"


def test_manager_can_reject(client, actor, uid):
    """[functional] A manager can reject a submitted request."""
    created = _submit(client, actor, uid("emp")).json()
    r = client.post(f"/leave-requests/{created['id']}/reject", headers=actor(uid("mgr"), "manager"))
    assert r.status_code == 200 and r.json()["status"] == "rejected"


def test_same_day_leave_is_allowed(client, actor, uid):
    """[functional] End date equal to start date is allowed (end may not precede start)."""
    assert _submit(client, actor, uid("emp"), start_date="2026-11-02", end_date="2026-11-02").status_code == 201


def test_requester_cannot_self_approve_even_as_manager(client, actor, uid):
    """[safety] The requester cannot approve their own request even when presenting the manager role."""
    who = uid("emp")
    created = _submit(client, actor, who).json()
    assert client.post(f"/leave-requests/{created['id']}/approve", headers=actor(who, "manager")).status_code == 403
    assert client.get(f"/leave-requests/{created['id']}", headers=actor(who, "employee")).json()["status"] == "submitted"


def test_employee_role_cannot_decide(client, actor, uid):
    """[safety] The employee role cannot approve or reject."""
    created = _submit(client, actor, uid("emp")).json()
    assert client.post(f"/leave-requests/{created['id']}/approve", headers=actor(uid("e"), "employee")).status_code == 403
    assert client.post(f"/leave-requests/{created['id']}/reject", headers=actor(uid("e"), "employee")).status_code == 403


def test_only_employees_submit(client, actor, uid):
    """[safety] Submitting with a non-employee role or without identity headers is 403."""
    assert _submit(client, actor, uid("emp")).status_code == 201
    body = {"reason": "x", "start_date": "2026-11-02", "end_date": "2026-11-03"}
    assert client.post("/leave-requests", json=body, headers=actor(uid("m"), "manager")).status_code == 403
    assert client.post("/leave-requests", json=body).status_code == 403


def test_end_before_start_is_422(client, actor, uid):
    """[safety] An end date before the start date is rejected with 422."""
    assert _submit(client, actor, uid("emp"), start_date="2026-11-08", end_date="2026-11-05").status_code == 422


def test_caller_cannot_set_status_or_requester(client, actor, uid):
    """[safety] Caller-supplied status or requester_id fields are rejected with 422."""
    assert _submit(client, actor, uid("emp"), status="approved").status_code == 422
    assert _submit(client, actor, uid("emp"), requester_id="someone_else").status_code == 422


def test_terminal_decisions_cannot_change(client, actor, uid):
    """[safety] Once approved or rejected, any further decision is 409 and the status stays."""
    a = _submit(client, actor, uid("emp")).json()
    assert client.post(f"/leave-requests/{a['id']}/approve", headers=actor(uid("m"), "manager")).status_code == 200
    assert client.post(f"/leave-requests/{a['id']}/reject", headers=actor(uid("m"), "manager")).status_code == 409
    b = _submit(client, actor, uid("emp")).json()
    assert client.post(f"/leave-requests/{b['id']}/reject", headers=actor(uid("m"), "manager")).status_code == 200
    assert client.post(f"/leave-requests/{b['id']}/approve", headers=actor(uid("m"), "manager")).status_code == 409
    assert client.get(f"/leave-requests/{b['id']}", headers=actor(uid("m"), "manager")).json()["status"] == "rejected"


def test_unknown_request_is_404(client, actor, uid):
    """[functional] Deciding an unknown request id is 404 (while the routes exist)."""
    assert _submit(client, actor, uid("emp")).status_code == 201
    assert client.post("/leave-requests/nope/approve", headers=actor(uid("m"), "manager")).status_code == 404


def test_blank_reason_is_422(client, actor, uid):
    """[safety] A blank reason is rejected with 422."""
    assert _submit(client, actor, uid("emp"), reason="   ").status_code == 422
