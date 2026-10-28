def _submit(client, actor, who, **over):
    body = {"amount": 125.5, "description": "Conference taxi"}
    body.update(over)
    return client.post("/expense-requests", json=body, headers=actor(who, "employee"))


def test_submit_returns_201_submitted(client, actor, uid):
    """[functional] An employee's valid submission is 201 with status submitted and requester from the header."""
    who = uid("emp")
    r = _submit(client, actor, who)
    assert r.status_code == 201 and r.json()["status"] == "submitted" and r.json()["requester_id"] == who


def test_request_can_be_read(client, actor, uid):
    """[functional] A submitted request can be read back by id."""
    created = _submit(client, actor, uid("emp")).json()
    assert client.get(f"/expense-requests/{created['id']}", headers=actor(uid("m"), "manager")).json()["amount"] == 125.5


def test_manager_can_approve(client, actor, uid):
    """[functional] A different manager can approve and the decision records who decided."""
    created = _submit(client, actor, uid("emp")).json()
    mgr = uid("mgr")
    r = client.post(f"/expense-requests/{created['id']}/approve", headers=actor(mgr, "manager"))
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["decided_by"] == mgr


def test_manager_can_reject(client, actor, uid):
    """[functional] A manager can reject a submitted request."""
    created = _submit(client, actor, uid("emp")).json()
    r = client.post(f"/expense-requests/{created['id']}/reject", headers=actor(uid("mgr"), "manager"))
    assert r.status_code == 200 and r.json()["status"] == "rejected"


def test_employee_cannot_approve_or_reject(client, actor, uid):
    """[safety] The employee role cannot approve or reject, and the request stays submitted."""
    created = _submit(client, actor, uid("emp")).json()
    assert client.post(f"/expense-requests/{created['id']}/approve", headers=actor(uid("e"), "employee")).status_code == 403
    assert client.post(f"/expense-requests/{created['id']}/reject", headers=actor(uid("e"), "employee")).status_code == 403
    assert client.get(f"/expense-requests/{created['id']}", headers=actor(uid("m"), "manager")).json()["status"] == "submitted"


def test_requester_cannot_self_approve_even_as_manager(client, actor, uid):
    """[safety] A requester presenting the manager role cannot approve or reject their own request."""
    who = uid("emp")
    created = _submit(client, actor, who).json()
    assert client.post(f"/expense-requests/{created['id']}/approve", headers=actor(who, "manager")).status_code == 403
    assert client.post(f"/expense-requests/{created['id']}/reject", headers=actor(who, "manager")).status_code == 403


def test_terminal_decisions_cannot_change(client, actor, uid):
    """[safety] Approved and rejected requests reject opposite decisions and preserve state."""
    rejected = _submit(client, actor, uid("emp-r")).json()
    assert client.post(f"/expense-requests/{rejected['id']}/reject", headers=actor(uid("m-r"), "manager")).status_code == 200
    assert client.post(f"/expense-requests/{rejected['id']}/approve", headers=actor(uid("m-r2"), "manager")).status_code == 409
    assert client.get(f"/expense-requests/{rejected['id']}", headers=actor(uid("m-r3"), "manager")).json()["status"] == "rejected"

    approved = _submit(client, actor, uid("emp-a")).json()
    assert client.post(f"/expense-requests/{approved['id']}/approve", headers=actor(uid("m-a"), "manager")).status_code == 200
    assert client.post(f"/expense-requests/{approved['id']}/reject", headers=actor(uid("m-a2"), "manager")).status_code == 409
    assert client.get(f"/expense-requests/{approved['id']}", headers=actor(uid("m-a3"), "manager")).json()["status"] == "approved"


def test_approval_is_not_repeatable(client, actor, uid):
    """[safety] Repeating either approval or rejection on a terminal request is 409."""
    approved = _submit(client, actor, uid("emp-a")).json()
    assert client.post(f"/expense-requests/{approved['id']}/approve", headers=actor(uid("m-a"), "manager")).status_code == 200
    assert client.post(f"/expense-requests/{approved['id']}/approve", headers=actor(uid("m-a2"), "manager")).status_code == 409

    rejected = _submit(client, actor, uid("emp-r")).json()
    assert client.post(f"/expense-requests/{rejected['id']}/reject", headers=actor(uid("m-r"), "manager")).status_code == 200
    assert client.post(f"/expense-requests/{rejected['id']}/reject", headers=actor(uid("m-r2"), "manager")).status_code == 409


def test_status_and_requester_injection_is_422(client, actor, uid):
    """[safety] Caller-supplied status, requester_id or decided_by fields are rejected with 422."""
    for field, value in (("status", "approved"), ("requester_id", "other"), ("decided_by", "me")):
        assert _submit(client, actor, uid("emp"), **{field: value}).status_code == 422, field


def test_small_positive_amount_is_accepted(client, actor, uid):
    """[functional] A small positive amount such as 0.5 is accepted."""
    r = _submit(client, actor, uid("emp"), amount=0.5)
    assert r.status_code == 201 and r.json()["amount"] == 0.5


def test_nonpositive_or_non_numeric_amount_is_422(client, actor, uid):
    """[safety] Zero, negative or non-numeric amounts are rejected with 422."""
    for amount in (0, -10, "lots"):
        assert _submit(client, actor, uid("emp"), amount=amount).status_code == 422, amount


def test_blank_description_is_422(client, actor, uid):
    """[safety] A whitespace-only description is rejected with 422."""
    assert _submit(client, actor, uid("emp"), description="   ").status_code == 422


def test_missing_identity_is_rejected(client, actor, uid):
    """[safety] Missing, partial or invalid identity headers are rejected with 403."""
    created = _submit(client, actor, uid("emp")).json()
    body = {"amount": 5, "description": "x"}
    assert client.post("/expense-requests", json=body).status_code == 403
    assert client.post("/expense-requests", json=body, headers={"x-actor-id": uid("partial")}).status_code == 403
    assert client.post("/expense-requests", json=body, headers=actor(uid("wrong"), "manager")).status_code == 403
    assert client.post(f"/expense-requests/{created['id']}/approve").status_code == 403
    assert client.post(f"/expense-requests/{created['id']}/approve", headers={"x-actor-role": "manager"}).status_code == 403
    assert client.post(f"/expense-requests/{created['id']}/approve", headers=actor(uid("wrong"), "employee")).status_code == 403


def test_unknown_request_is_404(client, actor, uid):
    """[functional] Deciding an unknown request id is 404 (while the routes exist)."""
    assert _submit(client, actor, uid("emp")).status_code == 201
    assert client.post("/expense-requests/nope/reject", headers=actor(uid("m"), "manager")).status_code == 404
