def _open(client, actor, who):
    r = client.post("/tickets", json={"title": "Printer", "description": "Jammed"}, headers=actor(who, "customer"))
    assert r.status_code == 201
    return r.json()["id"]


def _act(client, actor, tid, action, who, role):
    return client.post(f"/tickets/{tid}/{action}", headers=actor(who, role))


def _resolved(client, actor, uid, customer):
    tid = _open(client, actor, customer)
    assert _act(client, actor, tid, "start", uid("a"), "agent").status_code == 200
    assert _act(client, actor, tid, "resolve", uid("a"), "agent").status_code == 200
    return tid


def _status(client, actor, tid):
    return client.get(f"/tickets/{tid}", headers=actor("m", "manager")).json()["status"]


def test_open_ticket_is_201_open(client, actor, uid):
    """[functional] A customer opens a ticket: 201, status open, requester from the header."""
    who = uid("c")
    r = client.post("/tickets", json={"title": "A", "description": "B"}, headers=actor(who, "customer"))
    assert r.status_code == 201 and r.json()["status"] == "open" and r.json()["requester_id"] == who


def test_agent_starts_and_resolves(client, actor, uid):
    """[functional] An agent moves open -> in_progress -> resolved."""
    tid = _open(client, actor, uid("c"))
    assert _act(client, actor, tid, "start", uid("a"), "agent").json()["status"] == "in_progress"
    assert _act(client, actor, tid, "resolve", uid("a"), "agent").json()["status"] == "resolved"


def test_requester_closes_resolved_ticket(client, actor, uid):
    """[functional] The requesting customer closes a resolved ticket."""
    who = uid("c")
    tid = _resolved(client, actor, uid, who)
    assert _act(client, actor, tid, "close", who, "customer").json()["status"] == "closed"


def test_resolved_ticket_can_be_reopened_by_requester_or_agent(client, actor, uid):
    """[functional] A resolved ticket goes back to in_progress when the requester or an agent reopens it."""
    who = uid("c")
    tid = _resolved(client, actor, uid, who)
    assert _act(client, actor, tid, "reopen", who, "customer").json()["status"] == "in_progress"
    assert _act(client, actor, tid, "resolve", uid("a"), "agent").status_code == 200
    assert _act(client, actor, tid, "reopen", uid("a"), "agent").json()["status"] == "in_progress"


def test_manager_reopens_closed_ticket(client, actor, uid):
    """[functional] A manager reopens a closed ticket to in_progress."""
    who = uid("c")
    tid = _resolved(client, actor, uid, who)
    _act(client, actor, tid, "close", who, "customer")
    assert _act(client, actor, tid, "reopen", uid("m"), "manager").json()["status"] == "in_progress"


def test_closed_ticket_cannot_be_reopened_without_manager(client, actor, uid):
    """[safety] Requester or agent reopening a closed ticket is 403 and it stays closed."""
    who = uid("c")
    tid = _resolved(client, actor, uid, who)
    _act(client, actor, tid, "close", who, "customer")
    assert _act(client, actor, tid, "reopen", who, "customer").status_code == 403
    assert _act(client, actor, tid, "reopen", uid("a"), "agent").status_code == 403
    assert _status(client, actor, tid) == "closed"


def test_other_customer_cannot_reopen(client, actor, uid):
    """[safety] A customer who did not open the ticket cannot reopen it (403); it stays resolved."""
    tid = _resolved(client, actor, uid, uid("c"))
    assert _act(client, actor, tid, "reopen", uid("other"), "customer").status_code == 403
    assert _status(client, actor, tid) == "resolved"


def test_customer_cannot_resolve_or_start(client, actor, uid):
    """[safety] Customers cannot start or resolve tickets (403)."""
    who = uid("c")
    tid = _open(client, actor, who)
    assert _act(client, actor, tid, "start", who, "customer").status_code == 403
    _act(client, actor, tid, "start", uid("a"), "agent")
    assert _act(client, actor, tid, "resolve", who, "customer").status_code == 403
    assert _status(client, actor, tid) == "in_progress"


def test_other_customer_cannot_close(client, actor, uid):
    """[safety] A customer who did not open the ticket cannot close it (403)."""
    tid = _resolved(client, actor, uid, uid("c"))
    assert _act(client, actor, tid, "close", uid("other"), "customer").status_code == 403
    assert _status(client, actor, tid) == "resolved"


def test_status_order_is_enforced(client, actor, uid):
    """[safety] Resolving an open ticket, closing an in-progress ticket, or starting twice is 409."""
    who = uid("c")
    tid = _open(client, actor, who)
    assert _act(client, actor, tid, "resolve", uid("a"), "agent").status_code == 409
    assert _act(client, actor, tid, "start", uid("a"), "agent").status_code == 200
    assert _act(client, actor, tid, "start", uid("a"), "agent").status_code == 409
    assert _act(client, actor, tid, "close", who, "customer").status_code == 409


def test_closing_twice_is_409(client, actor, uid):
    """[safety] Closing an already closed ticket is 409."""
    who = uid("c")
    tid = _resolved(client, actor, uid, who)
    assert _act(client, actor, tid, "close", who, "customer").status_code == 200
    assert _act(client, actor, tid, "close", who, "customer").status_code == 409


def test_status_injection_is_422(client, actor, uid):
    """[safety] Caller-supplied status or requester_id on open is 422."""
    for field, value in (("status", "closed"), ("requester_id", "other")):
        body = {"title": "A", "description": "B", field: value}
        assert client.post("/tickets", json=body, headers=actor(uid("c"), "customer")).status_code == 422


def test_unknown_ticket_is_404(client, actor, uid):
    """[functional] Acting on an unknown ticket is 404 (while the routes exist)."""
    _open(client, actor, uid("c"))
    assert _act(client, actor, "nope", "start", uid("a"), "agent").status_code == 404


def test_missing_partial_or_unknown_identity_is_403(client, actor, uid):
    """[safety] Missing, partial or unknown-role identity headers are exactly 403 on every route and change nothing."""
    who = uid("c")
    tid = _open(client, actor, who)
    body = {"title": "A", "description": "B"}
    for headers in ({}, {"x-actor-id": who}, {"x-actor-role": "customer"}, actor(who, "visitor")):
        assert client.post("/tickets", json=body, headers=headers).status_code == 403, headers
        assert client.get(f"/tickets/{tid}", headers=headers).status_code == 403, headers
        for action in ("start", "resolve", "close", "reopen"):
            assert client.post(f"/tickets/{tid}/{action}", headers=headers).status_code == 403, (action, headers)
    assert _status(client, actor, tid) == "open"


def test_only_customers_can_open_tickets(client, actor, uid):
    """[safety] Agents and managers cannot open tickets (403)."""
    body = {"title": "A", "description": "B"}
    assert client.post("/tickets", json=body, headers=actor(uid("a"), "agent")).status_code == 403
    assert client.post("/tickets", json=body, headers=actor(uid("m"), "manager")).status_code == 403


def test_only_the_right_role_can_start_resolve_or_close(client, actor, uid):
    """[safety] Managers cannot start, resolve or close and agents cannot close (403); the status moves only for the right role."""
    who = uid("c")
    tid = _open(client, actor, who)
    assert _act(client, actor, tid, "start", uid("m"), "manager").status_code == 403
    assert _status(client, actor, tid) == "open"
    assert _act(client, actor, tid, "start", uid("a"), "agent").status_code == 200
    assert _act(client, actor, tid, "resolve", uid("m"), "manager").status_code == 403
    assert _status(client, actor, tid) == "in_progress"
    assert _act(client, actor, tid, "resolve", uid("a"), "agent").status_code == 200
    assert _act(client, actor, tid, "close", uid("m"), "manager").status_code == 403
    assert _act(client, actor, tid, "close", uid("a"), "agent").status_code == 403
    assert _status(client, actor, tid) == "resolved"


def test_actions_that_do_not_fit_the_status_are_409(client, actor, uid):
    """[safety] Reopening an open or in-progress ticket, and starting or resolving a resolved or closed one, is 409 and changes nothing."""
    who, agent = uid("c"), uid("a")
    tid = _open(client, actor, who)
    assert _act(client, actor, tid, "reopen", agent, "agent").status_code == 409
    assert _status(client, actor, tid) == "open"
    _act(client, actor, tid, "start", agent, "agent")
    assert _act(client, actor, tid, "reopen", agent, "agent").status_code == 409
    assert _status(client, actor, tid) == "in_progress"
    _act(client, actor, tid, "resolve", agent, "agent")
    assert _act(client, actor, tid, "start", agent, "agent").status_code == 409
    assert _act(client, actor, tid, "resolve", agent, "agent").status_code == 409
    assert _status(client, actor, tid) == "resolved"
    _act(client, actor, tid, "close", who, "customer")
    assert _act(client, actor, tid, "start", agent, "agent").status_code == 409
    assert _act(client, actor, tid, "resolve", agent, "agent").status_code == 409
    assert _status(client, actor, tid) == "closed"


def test_reopened_ticket_can_go_around_the_lifecycle_again(client, actor, uid):
    """[functional] After a manager reopens a closed ticket it is resolved and closed again, still by its original requester."""
    who = uid("c")
    tid = _resolved(client, actor, uid, who)
    assert _act(client, actor, tid, "close", who, "customer").status_code == 200
    assert _act(client, actor, tid, "reopen", uid("m"), "manager").json()["status"] == "in_progress"
    assert _act(client, actor, tid, "resolve", uid("a"), "agent").json()["status"] == "resolved"
    assert _act(client, actor, tid, "close", uid("other"), "customer").status_code == 403
    r = _act(client, actor, tid, "close", who, "customer")
    assert r.status_code == 200 and r.json()["status"] == "closed" and r.json()["requester_id"] == who


def test_response_fields_match_the_interface(client, actor, uid):
    """[functional] Open, read and every transition return id, requester_id, title, description and status; all roles can read."""
    fields = {"id", "requester_id", "title", "description", "status"}
    who = uid("c")
    opened = client.post("/tickets", json={"title": "Printer", "description": "Jammed"}, headers=actor(who, "customer"))
    assert opened.status_code == 201 and fields <= set(opened.json())
    assert opened.json()["title"] == "Printer" and opened.json()["description"] == "Jammed"
    tid = opened.json()["id"]
    for role, actor_id in (("customer", who), ("agent", uid("a")), ("manager", uid("m"))):
        r = client.get(f"/tickets/{tid}", headers=actor(actor_id, role))
        assert r.status_code == 200 and fields <= set(r.json()), role
    for action, actor_id, role in (("start", uid("a"), "agent"), ("resolve", uid("a"), "agent"), ("close", who, "customer")):
        r = _act(client, actor, tid, action, actor_id, role)
        assert r.status_code == 200 and fields <= set(r.json()), action


def test_unknown_ticket_is_404_on_every_route(client, actor, uid):
    """[functional] Reading or acting on an unknown ticket id is 404 when the caller has the right role."""
    _open(client, actor, uid("c"))
    assert client.get("/tickets/nope", headers=actor(uid("a"), "agent")).status_code == 404
    for action, role in (("start", "agent"), ("resolve", "agent"), ("close", "customer"), ("reopen", "agent")):
        assert _act(client, actor, "nope", action, uid("x"), role).status_code == 404, action


def test_empty_or_missing_title_and_description_are_422(client, actor, uid):
    """[safety] An empty or missing title or description is rejected with 422."""
    headers = actor(uid("c"), "customer")
    ok = {"title": "A", "description": "B"}
    for field in ok:
        assert client.post("/tickets", json={**ok, field: ""}, headers=headers).status_code == 422, field
        body = {key: value for key, value in ok.items() if key != field}
        assert client.post("/tickets", json=body, headers=headers).status_code == 422, field
