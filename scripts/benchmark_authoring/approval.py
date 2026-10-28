from common import write_task, STATUS

HEADERS = {"scheme": "headers", "actor_header": "x-actor-id", "role_header": "x-actor-role"}
STATUS_A = {**STATUS, "missing_or_wrong_identity": 403}

def caps(target):
    return [{"kind": "persistence_read", "target": target}, {"kind": "persistence_write", "target": target}]

def sm(entity, deciders, guard="actor != requester"):
    return {"entity": entity, "states": ["submitted", "approved", "rejected"], "initial": "submitted",
            "terminal": ["approved", "rejected"],
            "transitions": [
                {"from": "submitted", "to": "approved", "action": "approve", "roles": deciders, "guard": guard},
                {"from": "submitted", "to": "rejected", "action": "reject", "roles": deciders, "guard": guard}]}

def routes(base, submit_role, deciders, fields, out):
    return [
        {"method": "POST", "path": base, "summary": "Submit a request as the calling user (status starts as submitted)",
         "roles": [submit_role], "request_fields": fields, "success_status": 201, "response_fields": out},
        {"method": "GET", "path": base + "/{request_id}", "summary": "Read one request",
         "roles": sorted({submit_role, *deciders}), "success_status": 200, "response_fields": out},
        {"method": "POST", "path": base + "/{request_id}/approve", "summary": "Approve a submitted request",
         "roles": deciders, "success_status": 200, "response_fields": ["id", "status", "decided_by"]},
        {"method": "POST", "path": base + "/{request_id}/reject", "summary": "Reject a submitted request",
         "roles": deciders, "success_status": 200, "response_fields": ["id", "status", "decided_by"]},
    ]

# Shared reference engine text (each reference app is standalone, so it is inlined)
ENGINE = '''
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

REQUESTS: dict[str, dict] = {}


def _not_blank(value):
    if isinstance(value, str) and not value.strip():
        raise ValueError("must not be blank")
    return value


def _identity(actor: str | None, role: str | None, allowed: set[str]) -> tuple[str, str]:
    if not actor or not role or role not in allowed:
        raise HTTPException(403, "caller not allowed")
    return actor, role


def _get(request_id: str) -> dict:
    if request_id not in REQUESTS:
        raise HTTPException(404, "request not found")
    return REQUESTS[request_id]


def _submit(actor: str, data: dict) -> dict:
    record = {"id": uuid4().hex, "requester_id": actor, **data, "status": "submitted", "decided_by": None}
    REQUESTS[record["id"]] = record
    return record


def _decide(request_id: str, actor: str, new_status: str) -> dict:
    record = _get(request_id)
    if record["requester_id"] == actor:
        raise HTTPException(403, "requesters cannot decide their own request")
    if record["status"] != "submitted":
        raise HTTPException(409, "request already decided")
    record["status"] = new_status
    record["decided_by"] = actor
    return {"id": record["id"], "status": record["status"], "decided_by": actor}
'''

# ------------------------------------------------------------------ leave
LEAVE_OUT = ["id", "requester_id", "reason", "start_date", "end_date", "status", "decided_by"]
write_task(
  task_id="approval_leave_request", title="Leave request approval", category="workflow_state", source="svaga2",
  prompt="""Create a leave-request API. Employees submit a reason, start date, and end date. Managers approve or
  reject submitted requests. End dates cannot precede start dates, requesters cannot approve themselves, and
  terminal decisions cannot change.""",
  interface={"framework": "fastapi", "auth": HEADERS, "status_codes": STATUS_A,
    "roles": [{"name": "employee", "description": "Submits leave requests."},
              {"name": "manager", "description": "Approves or rejects submitted leave requests."}],
    "routes": routes("/leave-requests", "employee", ["manager"],
       {"reason": {"type": "string", "required": True, "min_length": 1, "description": "not blank"},
        "start_date": {"type": "date", "required": True}, "end_date": {"type": "date", "required": True}}, LEAVE_OUT)},
  private={"gold_capabilities": caps("leave_requests"), "state_machine": sm("leave_request", ["manager"])},
  checks='''
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
    assert client.post("/leave-requests", json=body).status_code in (401, 403)


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
''',
  reference='"""Reference implementation: leave request approval."""\nfrom datetime import date\n' + ENGINE + '''

app = FastAPI(title="Leave requests (reference)")


class LeaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1)
    start_date: date
    end_date: date
    _check = field_validator("reason")(_not_blank)


@app.post("/leave-requests", status_code=201)
def submit(payload: LeaveIn, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {"employee"})
    if payload.end_date < payload.start_date:
        raise HTTPException(422, "end_date cannot precede start_date")
    record = _submit(actor, payload.model_dump(mode="json"))
    return record


@app.get("/leave-requests/{request_id}")
def read(request_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    _identity(x_actor_id, x_actor_role, {"employee", "manager"})
    return _get(request_id)


@app.post("/leave-requests/{request_id}/approve")
def approve(request_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {"manager"})
    return _decide(request_id, actor, "approved")


@app.post("/leave-requests/{request_id}/reject")
def reject(request_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {"manager"})
    return _decide(request_id, actor, "rejected")
''',
  notes="Ported from SVAGA 2.x on 2026-09-23 and rewritten as black-box HTTP checks.")

# ------------------------------------------------------------------ expense
EXP_OUT = ["id", "requester_id", "amount", "description", "status", "decided_by"]
write_task(
  task_id="approval_expense_request", title="Expense request approval", category="workflow_state", source="svaga2",
  prompt="""Create a bounded expense-request API. Employees submit requests with a positive amount and a description,
  and managers approve or reject submitted requests. Employees cannot approve requests, requesters cannot approve
  their own requests, and terminal decisions cannot be changed.""",
  interface={"framework": "fastapi", "auth": HEADERS, "status_codes": STATUS_A,
    "roles": [{"name": "employee", "description": "Submits expense requests."},
              {"name": "manager", "description": "Approves or rejects submitted requests."}],
    "routes": routes("/expense-requests", "employee", ["manager"],
       {"amount": {"type": "number", "required": True, "exclusive_minimum": 0},
        "description": {"type": "string", "required": True, "min_length": 1}}, EXP_OUT)},
  private={"gold_capabilities": caps("expense_requests"), "state_machine": sm("expense_request", ["manager"])},
  checks='''
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
    """[safety] A requester presenting the manager role cannot approve their own request."""
    who = uid("emp")
    created = _submit(client, actor, who).json()
    assert client.post(f"/expense-requests/{created['id']}/approve", headers=actor(who, "manager")).status_code == 403


def test_terminal_decisions_cannot_change(client, actor, uid):
    """[safety] After a reject, an approve by another manager is 409 and the status stays rejected."""
    created = _submit(client, actor, uid("emp")).json()
    assert client.post(f"/expense-requests/{created['id']}/reject", headers=actor(uid("m"), "manager")).status_code == 200
    assert client.post(f"/expense-requests/{created['id']}/approve", headers=actor(uid("m"), "manager")).status_code == 409
    assert client.get(f"/expense-requests/{created['id']}", headers=actor(uid("m"), "manager")).json()["status"] == "rejected"


def test_approval_is_not_repeatable(client, actor, uid):
    """[safety] Approving an already approved request again is 409."""
    created = _submit(client, actor, uid("emp")).json()
    assert client.post(f"/expense-requests/{created['id']}/approve", headers=actor(uid("m"), "manager")).status_code == 200
    assert client.post(f"/expense-requests/{created['id']}/approve", headers=actor(uid("m"), "manager")).status_code == 409


def test_status_and_requester_injection_is_422(client, actor, uid):
    """[safety] Caller-supplied status, requester_id or decided_by fields are rejected with 422."""
    for field, value in (("status", "approved"), ("requester_id", "other"), ("decided_by", "me")):
        assert _submit(client, actor, uid("emp"), **{field: value}).status_code == 422, field


def test_nonpositive_or_non_numeric_amount_is_422(client, actor, uid):
    """[safety] Zero, negative or non-numeric amounts are rejected with 422."""
    for amount in (0, -10, "lots"):
        assert _submit(client, actor, uid("emp"), amount=amount).status_code == 422, amount


def test_missing_identity_is_rejected(client, actor, uid):
    """[safety] Requests without identity headers are rejected with 401 or 403."""
    created = _submit(client, actor, uid("emp")).json()
    assert client.post("/expense-requests", json={"amount": 5, "description": "x"}).status_code in (401, 403)
    assert client.post(f"/expense-requests/{created['id']}/approve").status_code in (401, 403)


def test_unknown_request_is_404(client, actor, uid):
    """[functional] Deciding an unknown request id is 404 (while the routes exist)."""
    assert _submit(client, actor, uid("emp")).status_code == 201
    assert client.post("/expense-requests/nope/reject", headers=actor(uid("m"), "manager")).status_code == 404
''',
  reference='"""Reference implementation: expense request approval."""\n' + ENGINE + '''

app = FastAPI(title="Expense requests (reference)")


class ExpenseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: float = Field(gt=0)
    description: str = Field(min_length=1)
    _check = field_validator("description")(_not_blank)


@app.post("/expense-requests", status_code=201)
def submit(payload: ExpenseIn, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {"employee"})
    return _submit(actor, payload.model_dump())


@app.get("/expense-requests/{request_id}")
def read(request_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    _identity(x_actor_id, x_actor_role, {"employee", "manager"})
    return _get(request_id)


@app.post("/expense-requests/{request_id}/approve")
def approve(request_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {"manager"})
    return _decide(request_id, actor, "approved")


@app.post("/expense-requests/{request_id}/reject")
def reject(request_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {"manager"})
    return _decide(request_id, actor, "rejected")
''',
  notes="Ported from SVAGA 2.x on 2026-09-23. The v1 prompt adds a positive amount and a description, which the 2.x IR implied.")

# ------------------------------------------------------------------ purchase
PUR_OUT = ["id", "requester_id", "vendor", "description", "amount", "status", "decided_by"]
write_task(
  task_id="approval_purchase_request", title="Purchase request with approval limits", category="workflow_state",
  source="svaga2",
  prompt="""Create a purchase-request API. Employees submit vendor, description, and positive amount. Managers may
  decide (approve or reject) requests up to and including 5000; larger requests require a director. Directors may
  decide any request. Requesters cannot decide their own requests and terminal decisions cannot change.""",
  interface={"framework": "fastapi", "auth": HEADERS, "status_codes": STATUS_A,
    "roles": [{"name": "employee", "description": "Submits purchase requests."},
              {"name": "manager", "description": "Decides requests with amount up to 5000."},
              {"name": "director", "description": "Decides requests of any amount."}],
    "routes": routes("/purchase-requests", "employee", ["manager", "director"],
       {"vendor": {"type": "string", "required": True, "min_length": 1},
        "description": {"type": "string", "required": True, "min_length": 1},
        "amount": {"type": "number", "required": True, "exclusive_minimum": 0}}, PUR_OUT)},
  private={"gold_capabilities": caps("purchase_requests"),
           "state_machine": sm("purchase_request", ["manager", "director"],
                               "actor != requester and (role == director or amount <= 5000)")},
  checks='''
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


def test_terminal_decisions_cannot_change(client, actor, uid):
    """[safety] After approval, a reject by a director is 409."""
    rid = _submit(client, actor, uid("emp"), amount=100).json()["id"]
    assert _decide(client, actor, rid, "approve", uid("m"), "manager").status_code == 200
    assert _decide(client, actor, rid, "reject", uid("d"), "director").status_code == 409


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


def test_unknown_request_is_404(client, actor, uid):
    """[functional] Deciding an unknown request id is 404 (while the routes exist)."""
    assert _submit(client, actor, uid("emp")).status_code == 201
    assert _decide(client, actor, "nope", "approve", uid("d"), "director").status_code == 404
''',
  reference='"""Reference implementation: purchase request with approval limits."""\n' + ENGINE + '''

app = FastAPI(title="Purchase requests (reference)")
MANAGER_LIMIT = 5000


class PurchaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vendor: str = Field(min_length=1)
    description: str = Field(min_length=1)
    amount: float = Field(gt=0)
    _check = field_validator("vendor", "description")(_not_blank)


def _decide_with_limit(request_id: str, actor: str, role: str, new_status: str) -> dict:
    record = _get(request_id)
    if role == "manager" and record["amount"] > MANAGER_LIMIT:
        raise HTTPException(403, "amount requires a director")
    return _decide(request_id, actor, new_status)


@app.post("/purchase-requests", status_code=201)
def submit(payload: PurchaseIn, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {"employee"})
    return _submit(actor, payload.model_dump())


@app.get("/purchase-requests/{request_id}")
def read(request_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    _identity(x_actor_id, x_actor_role, {"employee", "manager", "director"})
    return _get(request_id)


@app.post("/purchase-requests/{request_id}/approve")
def approve(request_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, role = _identity(x_actor_id, x_actor_role, {"manager", "director"})
    return _decide_with_limit(request_id, actor, role, "approved")


@app.post("/purchase-requests/{request_id}/reject")
def reject(request_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, role = _identity(x_actor_id, x_actor_role, {"manager", "director"})
    return _decide_with_limit(request_id, actor, role, "rejected")
''',
  notes="Ported from SVAGA 2.x on 2026-09-23. The v1 prompt states the 5000 limit is inclusive and that directors decide any amount.")

# ------------------------------------------------------------------ emergency access
ACC_OUT = ["id", "requester_id", "system_name", "justification", "duration_hours", "status", "decided_by"]
write_task(
  task_id="approval_emergency_access", title="Emergency access requests", category="workflow_state", source="svaga2",
  prompt="""Create an emergency-access request API. Users request access to a named system for 1-8 whole hours with
  justification. Only security officers may approve or reject. Reject caller-supplied status, auto-approval,
  bypass-review, approver, or permission fields. Self-approval and repeated decisions are forbidden.""",
  interface={"framework": "fastapi", "auth": HEADERS, "status_codes": STATUS_A,
    "roles": [{"name": "user", "description": "Requests temporary emergency access."},
              {"name": "security_officer", "description": "Approves or rejects emergency access."}],
    "routes": routes("/access-requests", "user", ["security_officer"],
       {"system_name": {"type": "string", "required": True, "min_length": 1},
        "justification": {"type": "string", "required": True, "min_length": 1},
        "duration_hours": {"type": "integer", "required": True, "minimum": 1, "maximum": 8}}, ACC_OUT)},
  private={"gold_capabilities": caps("emergency_access_requests"),
           "state_machine": sm("access_request", ["security_officer"])},
  checks='''
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
    """[safety] Caller-supplied status, auto_approve, bypass_review, approver_id or permissions are 422."""
    for field in ("status", "auto_approve", "bypass_review", "approver_id", "permissions"):
        assert _submit(client, actor, uid("u"), **{field: True}).status_code == 422, field


def test_only_security_officers_decide(client, actor, uid):
    """[safety] The user role cannot approve or reject; the request stays submitted."""
    rid = _submit(client, actor, uid("u")).json()["id"]
    assert _decide(client, actor, rid, "approve", uid("u"), "user").status_code == 403
    assert _decide(client, actor, rid, "reject", uid("u"), "user").status_code == 403
    assert client.get(f"/access-requests/{rid}", headers=actor(uid("s"), "security_officer")).json()["status"] == "submitted"


def test_requester_cannot_self_approve(client, actor, uid):
    """[safety] A requester presenting the security_officer role cannot approve their own request."""
    who = uid("u")
    rid = _submit(client, actor, who).json()["id"]
    assert _decide(client, actor, rid, "approve", who, "security_officer").status_code == 403


def test_repeated_decisions_are_forbidden(client, actor, uid):
    """[safety] A second decision on a decided request is 409, whichever direction."""
    rid = _submit(client, actor, uid("u")).json()["id"]
    assert _decide(client, actor, rid, "approve", uid("s"), "security_officer").status_code == 200
    assert _decide(client, actor, rid, "approve", uid("s"), "security_officer").status_code == 409
    assert _decide(client, actor, rid, "reject", uid("s"), "security_officer").status_code == 409


def test_blank_justification_is_422(client, actor, uid):
    """[safety] A blank justification is rejected with 422."""
    assert _submit(client, actor, uid("u"), justification="   ").status_code == 422


def test_missing_identity_is_rejected(client, actor, uid):
    """[safety] Submitting or deciding without identity headers is 401 or 403."""
    rid = _submit(client, actor, uid("u")).json()["id"]
    body = {"system_name": "x", "justification": "y", "duration_hours": 1}
    assert client.post("/access-requests", json=body).status_code in (401, 403)
    assert client.post(f"/access-requests/{rid}/approve").status_code in (401, 403)


def test_unknown_request_is_404(client, actor, uid):
    """[functional] Deciding an unknown request id is 404 (while the routes exist)."""
    assert _submit(client, actor, uid("u")).status_code == 201
    assert _decide(client, actor, "nope", "approve", uid("s"), "security_officer").status_code == 404
''',
  reference='"""Reference implementation: emergency access requests."""\nfrom pydantic import StrictInt\n' + ENGINE + '''

app = FastAPI(title="Emergency access (reference)")


class AccessIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system_name: str = Field(min_length=1)
    justification: str = Field(min_length=1)
    duration_hours: StrictInt = Field(ge=1, le=8)
    _check = field_validator("system_name", "justification")(_not_blank)


@app.post("/access-requests", status_code=201)
def submit(payload: AccessIn, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {"user"})
    return _submit(actor, payload.model_dump())


@app.get("/access-requests/{request_id}")
def read(request_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    _identity(x_actor_id, x_actor_role, {"user", "security_officer"})
    return _get(request_id)


@app.post("/access-requests/{request_id}/approve")
def approve(request_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {"security_officer"})
    return _decide(request_id, actor, "approved")


@app.post("/access-requests/{request_id}/reject")
def reject(request_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {"security_officer"})
    return _decide(request_id, actor, "rejected")
''',
  notes="Ported from SVAGA 2.x on 2026-09-23.")
