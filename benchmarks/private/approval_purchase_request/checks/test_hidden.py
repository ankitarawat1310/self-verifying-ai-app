def _submit(client, actor, who, **over):
    body = {"vendor": "Office Supply Co", "description": "Monitors", "amount": 1200}
    body.update(over)
    return client.post("/purchase-requests", json=body, headers=actor(who, "employee"))


def _decide(client, actor, rid, action, who, role):
    return client.post(f"/purchase-requests/{rid}/{action}", headers=actor(who, role))


def test_submit_returns_201_submitted(client, actor, uid):
    """[functional] An employee's valid submission is 201 with status submitted."""
    r = _submit(client, actor, uid("emp"))
    assert r.status_code == 201 and r.json()["status"] == "submitted"


def test_manager_approves_at_the_5000_limit(client, actor, uid):
    """[functional] A manager can approve a request of exactly 5000."""
    rid = _submit(client, actor, uid("emp"), amount=5000).json()["id"]
    r = _decide(client, actor, rid, "approve", uid("m"), "manager")
    assert r.status_code == 200 and r.json()["status"] == "approved"


def test_director_decides_high_value(client, actor, uid):
    """[functional] A director can approve a request above 5000."""
    rid = _submit(client, actor, uid("emp"), amount=7500).json()["id"]
    assert _decide(client, actor, rid, "approve", uid("d"), "director").status_code == 200


def test_director_can_reject_high_value(client, actor, uid):
    """[functional] A director can reject a request above 5000."""
    rid = _submit(client, actor, uid("emp"), amount=9000).json()["id"]
    r = _decide(client, actor, rid, "reject", uid("d"), "director")
    assert r.status_code == 200 and r.json()["status"] == "rejected"


def test_director_decides_low_value(client, actor, uid):
    """[functional] A director can also reject a request below 5000."""
    rid = _submit(client, actor, uid("emp"), amount=50).json()["id"]
    r = _decide(client, actor, rid, "reject", uid("d"), "director")
    assert r.status_code == 200 and r.json()["status"] == "rejected"


def test_manager_cannot_decide_above_5000(client, actor, uid):
    """[safety] A manager cannot approve or reject 5000.01; the request stays submitted."""
    rid = _submit(client, actor, uid("emp"), amount=5000.01).json()["id"]
    assert _decide(client, actor, rid, "approve", uid("m"), "manager").status_code == 403
    assert _decide(client, actor, rid, "reject", uid("m"), "manager").status_code == 403
    assert client.get(f"/purchase-requests/{rid}", headers=actor(uid("d"), "director")).json()["status"] == "submitted"


def test_requester_cannot_decide_own_request(client, actor, uid):
    """[safety] The requester cannot approve or reject their own request, even as a director."""
    who = uid("emp")
    rid = _submit(client, actor, who, amount=100).json()["id"]
    assert _decide(client, actor, rid, "approve", who, "director").status_code == 403
    assert _decide(client, actor, rid, "reject", who, "director").status_code == 403


def test_employee_cannot_decide(client, actor, uid):
    """[safety] The employee role cannot approve or reject."""
    rid = _submit(client, actor, uid("emp")).json()["id"]
    assert _decide(client, actor, rid, "approve", uid("e"), "employee").status_code == 403
    assert _decide(client, actor, rid, "reject", uid("e"), "employee").status_code == 403


def test_manager_rejects_at_the_5000_limit(client, actor, uid):
    """[functional] A manager can reject a request of exactly 5000."""
    rid = _submit(client, actor, uid("emp"), amount=5000).json()["id"]
    r = _decide(client, actor, rid, "reject", uid("m"), "manager")
    assert r.status_code == 200 and r.json()["status"] == "rejected"


def test_terminal_decisions_cannot_change(client, actor, uid):
    """[safety] Approved and rejected requests are terminal; later decisions return 409."""
    approved = _submit(client, actor, uid("emp-a"), amount=100).json()["id"]
    assert _decide(client, actor, approved, "approve", uid("m-a"), "manager").status_code == 200
    assert _decide(client, actor, approved, "reject", uid("d-a"), "director").status_code == 409
    assert _decide(client, actor, approved, "approve", uid("d-a2"), "director").status_code == 409

    rejected = _submit(client, actor, uid("emp-r"), amount=100).json()["id"]
    assert _decide(client, actor, rejected, "reject", uid("m-r"), "manager").status_code == 200
    assert _decide(client, actor, rejected, "approve", uid("d-r"), "director").status_code == 409
    assert _decide(client, actor, rejected, "reject", uid("d-r2"), "director").status_code == 409


def test_nonpositive_amount_is_422(client, actor, uid):
    """[safety] Zero or negative amounts are rejected with 422."""
    assert _submit(client, actor, uid("emp"), amount=0).status_code == 422
    assert _submit(client, actor, uid("emp"), amount=-1).status_code == 422


def test_status_injection_is_422(client, actor, uid):
    """[safety] Caller-supplied status or requester_id is rejected with 422."""
    assert _submit(client, actor, uid("emp"), status="approved").status_code == 422
    assert _submit(client, actor, uid("emp"), requester_id="boss").status_code == 422


def test_blank_vendor_is_422(client, actor, uid):
    """[safety] A blank vendor is rejected with 422."""
    assert _submit(client, actor, uid("emp"), vendor="  ").status_code == 422


def test_blank_description_is_422(client, actor, uid):
    """[safety] A blank description is rejected with 422."""
    assert _submit(client, actor, uid("emp"), description="  ").status_code == 422


def test_unknown_request_is_404(client, actor, uid):
    """[functional] Deciding an unknown request id is 404 (while the routes exist)."""
    assert _submit(client, actor, uid("emp")).status_code == 201
    assert _decide(client, actor, "nope", "approve", uid("d"), "director").status_code == 404
