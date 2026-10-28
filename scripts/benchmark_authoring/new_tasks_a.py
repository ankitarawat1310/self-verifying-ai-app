"""Benchmark v1: four tasks rewritten from scratch (SVAGA 3.0 ideas): billing invoice, role-scoped documents,
login lockout, ticket lifecycle."""
from common import write_task, STATUS

from snippets import CLOCK, CLOCK_FN, HEADERS, IDENTITY, NOT_BLANK, NO_AUTH, STATUS_A, caps

# =================================================================== billing invoice
INV_OUT = ["id", "customer", "line_items", "total", "status"]
LINE = {"description": {"type": "string", "required": True, "min_length": 1},
        "quantity": {"type": "integer", "required": True, "minimum": 1},
        "unit_price": {"type": "number", "required": True, "minimum": 0}}
write_task(
  task_id="billing_invoice", title="Invoices with computed totals", category="data_rules", source="svaga3",
  prompt="""Create an invoicing API. An invoice has a customer and at least one line item (description, whole-number
  quantity of at least 1, unit price of at least 0). The server computes the total as the sum of quantity times unit
  price, rounded to cents; clients can never set totals. Invoices start as draft. Line items can be added only while
  draft. A draft with line items can be issued, and only an issued invoice can be paid, with an amount exactly equal
  to its total.""",
  interface={"framework": "fastapi", "auth": NO_AUTH, "status_codes": STATUS,
    "roles": [{"name": "user", "description": "Any caller; no identity headers are used"}],
    "routes": [
      {"method": "POST", "path": "/invoices", "summary": "Create a draft invoice",
       "request_fields": {"customer": {"type": "string", "required": True, "min_length": 1},
                          "line_items": {"type": "array", "required": True,
                                         "description": "one or more objects with description, quantity, unit_price"}},
       "success_status": 201, "response_fields": INV_OUT},
      {"method": "GET", "path": "/invoices/{invoice_id}", "summary": "Read one invoice", "success_status": 200,
       "response_fields": INV_OUT},
      {"method": "POST", "path": "/invoices/{invoice_id}/line-items", "summary": "Add a line item to a draft invoice",
       "request_fields": LINE, "success_status": 200, "response_fields": INV_OUT},
      {"method": "POST", "path": "/invoices/{invoice_id}/issue", "summary": "Issue a draft invoice",
       "success_status": 200, "response_fields": INV_OUT},
      {"method": "POST", "path": "/invoices/{invoice_id}/pay", "summary": "Pay an issued invoice in full",
       "request_fields": {"amount": {"type": "number", "required": True, "exclusive_minimum": 0}},
       "success_status": 200, "response_fields": INV_OUT}]},
  private={"gold_capabilities": caps("invoices"),
           "state_machine": {"entity": "invoice", "states": ["draft", "issued", "paid"], "initial": "draft",
                             "terminal": ["paid"],
                             "transitions": [{"from": "draft", "to": "issued", "action": "issue", "roles": ["user"]},
                                             {"from": "issued", "to": "paid", "action": "pay", "roles": ["user"],
                                              "guard": "amount == total"}]}},
  checks='''
def _create(client, uid, items=None, **over):
    body = {"customer": uid("cust"), "line_items": items or [{"description": "Widget", "quantity": 2, "unit_price": 10}]}
    body.update(over)
    return client.post("/invoices", json=body)


def test_create_computes_total_and_starts_draft(client, uid):
    """[functional] A new invoice is 201, status draft, total = sum of quantity x unit price."""
    r = _create(client, uid, [{"description": "A", "quantity": 2, "unit_price": 10},
                              {"description": "B", "quantity": 1, "unit_price": 5.5}])
    assert r.status_code == 201
    assert r.json()["status"] == "draft" and r.json()["total"] == 25.5


def test_total_is_rounded_to_cents(client, uid):
    """[functional] Totals are exact to the cent: 0.10 + 0.20 is 0.30 and 3 x 1.10 is 3.30 (no floating-point residue)."""
    r = _create(client, uid, [{"description": "A", "quantity": 1, "unit_price": 0.1},
                              {"description": "B", "quantity": 1, "unit_price": 0.2}])
    assert r.status_code == 201 and r.json()["total"] == 0.3
    r = _create(client, uid, [{"description": "A", "quantity": 3, "unit_price": 1.1}])
    assert r.status_code == 201 and r.json()["total"] == 3.3
    r = _create(client, uid, [{"description": "A", "quantity": 3, "unit_price": 0.1},
                              {"description": "B", "quantity": 1, "unit_price": 19.99}])
    assert r.status_code == 201 and r.json()["total"] == 20.29


def test_adding_a_line_updates_the_total(client, uid):
    """[functional] Adding a line item to a draft updates the stored total."""
    inv = _create(client, uid).json()
    r = client.post(f"/invoices/{inv['id']}/line-items", json={"description": "C", "quantity": 4, "unit_price": 2.5})
    assert r.status_code == 200 and r.json()["total"] == 30
    assert client.get(f"/invoices/{inv['id']}").json()["total"] == 30


def test_issue_then_pay_exact_total(client, uid):
    """[functional] Issue a draft, then pay exactly the total: status paid."""
    inv = _create(client, uid).json()
    assert client.post(f"/invoices/{inv['id']}/issue").json()["status"] == "issued"
    r = client.post(f"/invoices/{inv['id']}/pay", json={"amount": 20})
    assert r.status_code == 200 and r.json()["status"] == "paid"


def test_client_cannot_set_total_or_status(client, uid):
    """[safety] total, subtotal or status in the create body are rejected with 422."""
    for field, value in (("total", 0), ("subtotal", 0), ("status", "paid")):
        assert _create(client, uid, **{field: value}).status_code == 422, field


def test_line_item_cannot_carry_its_own_total(client, uid):
    """[safety] A line item with an extra field such as line_total is rejected with 422."""
    items = [{"description": "A", "quantity": 1, "unit_price": 5, "line_total": 0}]
    assert _create(client, uid, items).status_code == 422


def test_empty_invoice_is_422(client, uid):
    """[safety] An invoice with no line items is rejected with 422."""
    assert client.post("/invoices", json={"customer": uid("c"), "line_items": []}).status_code == 422


def test_invalid_quantity_or_price_is_422(client, uid):
    """[safety] Quantity 0, fractional quantity, or a negative unit price is rejected with 422."""
    for item in ({"description": "A", "quantity": 0, "unit_price": 1},
                 {"description": "A", "quantity": 1.5, "unit_price": 1},
                 {"description": "A", "quantity": 1, "unit_price": -0.01}):
        assert _create(client, uid, [item]).status_code == 422, item


def test_no_line_items_after_issue(client, uid):
    """[safety] Adding a line to an issued invoice is 409 and the total does not change."""
    inv = _create(client, uid).json()
    client.post(f"/invoices/{inv['id']}/issue")
    r = client.post(f"/invoices/{inv['id']}/line-items", json={"description": "X", "quantity": 1, "unit_price": 99})
    assert r.status_code == 409
    assert client.get(f"/invoices/{inv['id']}").json()["total"] == 20


def test_wrong_payment_amount_is_422_and_unpaid(client, uid):
    """[safety] Paying less or more than the total is 422 and the invoice stays issued."""
    inv = _create(client, uid).json()
    client.post(f"/invoices/{inv['id']}/issue")
    assert client.post(f"/invoices/{inv['id']}/pay", json={"amount": 19.99}).status_code == 422
    assert client.post(f"/invoices/{inv['id']}/pay", json={"amount": 25}).status_code == 422
    assert client.get(f"/invoices/{inv['id']}").json()["status"] == "issued"


def test_state_order_is_enforced(client, uid):
    """[safety] Paying a draft is 409; issuing twice is 409; paying twice is 409."""
    inv = _create(client, uid).json()
    assert client.post(f"/invoices/{inv['id']}/pay", json={"amount": 20}).status_code == 409
    assert client.post(f"/invoices/{inv['id']}/issue").status_code == 200
    assert client.post(f"/invoices/{inv['id']}/issue").status_code == 409
    assert client.post(f"/invoices/{inv['id']}/pay", json={"amount": 20}).status_code == 200
    assert client.post(f"/invoices/{inv['id']}/pay", json={"amount": 20}).status_code == 409


def test_unknown_invoice_is_404(client, uid):
    """[functional] Reading or issuing an unknown invoice is 404 (while the routes exist)."""
    assert _create(client, uid).status_code == 201
    assert client.get("/invoices/nope").status_code == 404
    assert client.post("/invoices/nope/issue").status_code == 404
''',
  reference='''
"""Reference implementation: invoices with server-computed totals."""
from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
''' + NOT_BLANK + '''

app = FastAPI(title="Invoices (reference)")
INVOICES: dict[str, dict] = {}


class LineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1)
    quantity: StrictInt = Field(ge=1)
    unit_price: float = Field(ge=0)
    _check = field_validator("description")(_not_blank)


class InvoiceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer: str = Field(min_length=1)
    line_items: list[LineIn] = Field(min_length=1)
    _check = field_validator("customer")(_not_blank)


class PaymentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: float = Field(gt=0)


def _total(lines: list[dict]) -> float:
    total = sum(Decimal(str(l["quantity"])) * Decimal(str(l["unit_price"])) for l in lines)
    return float(Decimal(total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _get(invoice_id: str) -> dict:
    if invoice_id not in INVOICES:
        raise HTTPException(404, "invoice not found")
    return INVOICES[invoice_id]


@app.post("/invoices", status_code=201)
def create_invoice(payload: InvoiceIn) -> dict:
    lines = [l.model_dump() for l in payload.line_items]
    invoice = {"id": uuid4().hex, "customer": payload.customer, "line_items": lines, "total": _total(lines),
               "status": "draft"}
    INVOICES[invoice["id"]] = invoice
    return invoice


@app.get("/invoices/{invoice_id}")
def read_invoice(invoice_id: str) -> dict:
    return _get(invoice_id)


@app.post("/invoices/{invoice_id}/line-items")
def add_line(invoice_id: str, payload: LineIn) -> dict:
    invoice = _get(invoice_id)
    if invoice["status"] != "draft":
        raise HTTPException(409, "only draft invoices can change")
    invoice["line_items"].append(payload.model_dump())
    invoice["total"] = _total(invoice["line_items"])
    return invoice


@app.post("/invoices/{invoice_id}/issue")
def issue(invoice_id: str) -> dict:
    invoice = _get(invoice_id)
    if invoice["status"] != "draft" or not invoice["line_items"]:
        raise HTTPException(409, "only a draft with line items can be issued")
    invoice["status"] = "issued"
    return invoice


@app.post("/invoices/{invoice_id}/pay")
def pay(invoice_id: str, payload: PaymentIn) -> dict:
    invoice = _get(invoice_id)
    if invoice["status"] != "issued":
        raise HTTPException(409, "only issued invoices can be paid")
    if Decimal(str(payload.amount)).quantize(Decimal("0.01")) != Decimal(str(invoice["total"])).quantize(Decimal("0.01")):
        raise HTTPException(422, "amount must equal the invoice total")
    invoice["status"] = "paid"
    return invoice
''', notes="New task (Day 3) replacing SVAGA 3.0 billing_invoice, which had one route and one check.")

# =================================================================== role-scoped documents
DOC_OUT = ["id", "owner_id", "title", "body"]
write_task(
  task_id="role_scoped_documents", title="Documents visible only to their owner", category="access_control",
  source="svaga3",
  prompt="""Create a document API where each document belongs to the user who created it. Users can list, read,
  update and delete only their own documents; admins can list, read, update and delete every document. A user asking
  for another user's document gets 404, exactly as if it did not exist, and query parameters can never widen what a
  user sees. The owner is always the caller and cannot be supplied or changed by the client.""",
  interface={"framework": "fastapi", "auth": HEADERS, "status_codes": {**STATUS_A, "not_visible_to_caller": 404},
    "roles": [{"name": "user", "description": "Sees and changes only their own documents"},
              {"name": "admin", "description": "Sees and changes all documents"}],
    "routes": [
      {"method": "POST", "path": "/documents", "summary": "Create a document owned by the caller",
       "roles": ["user", "admin"],
       "request_fields": {"title": {"type": "string", "required": True, "min_length": 1},
                          "body": {"type": "string", "required": True}},
       "success_status": 201, "response_fields": DOC_OUT},
      {"method": "GET", "path": "/documents", "summary": "List documents visible to the caller",
       "roles": ["user", "admin"], "success_status": 200, "response_fields": DOC_OUT},
      {"method": "GET", "path": "/documents/{document_id}", "summary": "Read one visible document",
       "roles": ["user", "admin"], "success_status": 200, "response_fields": DOC_OUT},
      {"method": "PATCH", "path": "/documents/{document_id}", "summary": "Update title and/or body",
       "roles": ["user", "admin"],
       "request_fields": {"title": {"type": "string", "required": False, "min_length": 1},
                          "body": {"type": "string", "required": False}},
       "success_status": 200, "response_fields": DOC_OUT},
      {"method": "DELETE", "path": "/documents/{document_id}", "summary": "Delete a visible document",
       "roles": ["user", "admin"], "success_status": 204}]},
  private={"gold_capabilities": caps("documents")},
  checks='''
def _create(client, actor, who, role="user", **over):
    body = {"title": "Notes", "body": "secret plans"}
    body.update(over)
    return client.post("/documents", json=body, headers=actor(who, role))


def test_create_sets_owner_from_header(client, actor, uid):
    """[functional] A created document is 201 and owned by the caller."""
    who = uid("u")
    r = _create(client, actor, who)
    assert r.status_code == 201 and r.json()["owner_id"] == who


def test_owner_can_read_update_and_delete(client, actor, uid):
    """[functional] The owner can read, update and delete their document."""
    who = uid("u")
    doc = _create(client, actor, who).json()
    assert client.get(f"/documents/{doc['id']}", headers=actor(who, "user")).status_code == 200
    assert client.patch(f"/documents/{doc['id']}", json={"title": "New"}, headers=actor(who, "user")).json()["title"] == "New"
    assert client.delete(f"/documents/{doc['id']}", headers=actor(who, "user")).status_code == 204


def test_admin_sees_and_reads_everything(client, actor, uid):
    """[functional] An admin's list includes other users' documents and the admin can read them."""
    doc = _create(client, actor, uid("u")).json()
    ids = [d["id"] for d in client.get("/documents", headers=actor(uid("adm"), "admin")).json()]
    assert doc["id"] in ids
    assert client.get(f"/documents/{doc['id']}", headers=actor(uid("adm"), "admin")).status_code == 200


def test_list_shows_only_own_documents(client, actor, uid):
    """[safety] A user's list contains their documents and none of another user's."""
    alice, bob = uid("alice"), uid("bob")
    mine = _create(client, actor, alice).json()
    theirs = _create(client, actor, bob).json()
    listed = client.get("/documents", headers=actor(alice, "user")).json()
    ids = [d["id"] for d in listed]
    assert mine["id"] in ids and theirs["id"] not in ids
    assert all(d["owner_id"] == alice for d in listed)


def test_query_parameters_cannot_widen_the_list(client, actor, uid):
    """[safety] ?owner_id=, ?all=true or ?role=admin never reveal another user's documents."""
    alice, bob = uid("alice"), uid("bob")
    theirs = _create(client, actor, bob).json()
    _create(client, actor, alice)
    for params in ({"owner_id": bob}, {"all": "true"}, {"role": "admin"}):
        r = client.get("/documents", params=params, headers=actor(alice, "user"))
        assert r.status_code in (200, 422)
        if r.status_code == 200:
            assert theirs["id"] not in [d["id"] for d in r.json()], params


def test_reading_another_users_document_is_404(client, actor, uid):
    """[safety] Reading another user's document returns 404, same as a missing one."""
    doc = _create(client, actor, uid("bob")).json()
    assert client.get(f"/documents/{doc['id']}", headers=actor(uid("alice"), "user")).status_code == 404


def test_updating_another_users_document_is_404_and_unchanged(client, actor, uid):
    """[safety] PATCH on another user's document is 404 and the document is unchanged."""
    bob = uid("bob")
    doc = _create(client, actor, bob).json()
    r = client.patch(f"/documents/{doc['id']}", json={"body": "hacked"}, headers=actor(uid("alice"), "user"))
    assert r.status_code == 404
    assert client.get(f"/documents/{doc['id']}", headers=actor(bob, "user")).json()["body"] == "secret plans"


def test_deleting_another_users_document_is_404_and_it_survives(client, actor, uid):
    """[safety] DELETE on another user's document is 404 and the document still exists."""
    bob = uid("bob")
    doc = _create(client, actor, bob).json()
    assert client.delete(f"/documents/{doc['id']}", headers=actor(uid("alice"), "user")).status_code == 404
    assert client.get(f"/documents/{doc['id']}", headers=actor(bob, "user")).status_code == 200


def test_owner_cannot_be_supplied_or_changed(client, actor, uid):
    """[safety] owner_id in create or update bodies is rejected with 422."""
    who = uid("u")
    assert _create(client, actor, who, owner_id=uid("other")).status_code == 422
    doc = _create(client, actor, who).json()
    r = client.patch(f"/documents/{doc['id']}", json={"owner_id": uid("other")}, headers=actor(who, "user"))
    assert r.status_code == 422


def test_admin_can_delete_any_document(client, actor, uid):
    """[functional] An admin can delete another user's document."""
    bob = uid("bob")
    doc = _create(client, actor, bob).json()
    assert client.delete(f"/documents/{doc['id']}", headers=actor(uid("adm"), "admin")).status_code == 204
    assert client.get(f"/documents/{doc['id']}", headers=actor(bob, "user")).status_code == 404


def test_missing_or_unknown_role_is_rejected(client, actor, uid):
    """[safety] Calls without identity headers or with an unknown role are 401 or 403."""
    assert _create(client, actor, uid("u")).status_code == 201
    assert client.get("/documents").status_code in (401, 403)
    assert client.get("/documents", headers=actor(uid("x"), "superuser")).status_code in (401, 403)


def test_blank_title_is_422(client, actor, uid):
    """[safety] A blank title is rejected with 422."""
    assert _create(client, actor, uid("u"), title="  ").status_code == 422
''',
  reference='''
"""Reference implementation: documents visible only to their owner (admins see all)."""
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
''' + NOT_BLANK + IDENTITY + '''

app = FastAPI(title="Role-scoped documents (reference)")
DOCUMENTS: dict[str, dict] = {}
ROLES = {"user", "admin"}


class DocIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)
    body: str
    _check = field_validator("title")(_not_blank)


class DocPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1)
    body: str | None = None
    _check = field_validator("title")(_not_blank)


def _visible(document_id: str, actor: str, role: str) -> dict:
    doc = DOCUMENTS.get(document_id)
    if doc is None or (role != "admin" and doc["owner_id"] != actor):
        raise HTTPException(404, "document not found")
    return doc


@app.post("/documents", status_code=201)
def create(payload: DocIn, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, ROLES)
    doc = {"id": uuid4().hex, "owner_id": actor, **payload.model_dump()}
    DOCUMENTS[doc["id"]] = doc
    return doc


@app.get("/documents")
def list_documents(x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> list[dict]:
    actor, role = _identity(x_actor_id, x_actor_role, ROLES)
    return [d for d in DOCUMENTS.values() if role == "admin" or d["owner_id"] == actor]


@app.get("/documents/{document_id}")
def read(document_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, role = _identity(x_actor_id, x_actor_role, ROLES)
    return _visible(document_id, actor, role)


@app.patch("/documents/{document_id}")
def update(document_id: str, payload: DocPatch, x_actor_id: str | None = Header(None),
           x_actor_role: str | None = Header(None)) -> dict:
    actor, role = _identity(x_actor_id, x_actor_role, ROLES)
    doc = _visible(document_id, actor, role)
    doc.update(payload.model_dump(exclude_unset=True, exclude_none=True))
    return doc


@app.delete("/documents/{document_id}", status_code=204)
def delete(document_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> Response:
    actor, role = _identity(x_actor_id, x_actor_role, ROLES)
    _visible(document_id, actor, role)
    del DOCUMENTS[document_id]
    return Response(status_code=204)
''', notes="New task (Day 3) replacing SVAGA 3.0 role_scoped_list. Covers OWASP API1 (broken object-level authorization).")

# =================================================================== login lockout
write_task(
  task_id="login_lockout", title="Login with lockout after repeated failures", category="access_control",
  source="svaga3",
  prompt="""Create a user registration and login API. Usernames are unique and passwords have at least 8 characters;
  passwords are never returned in any response. Logging in with a wrong password or an unknown username returns 401.
  After 5 consecutive failed logins for the same username, that account is locked for 15 minutes: every login attempt
  during the lock returns 423, even with the correct password. A successful login resets the failure count. Use the
  test clock header as the current time when it is present.""",
  interface={"framework": "fastapi", "auth": NO_AUTH, "clock": CLOCK,
    "status_codes": {**STATUS, "wrong_credentials": 401, "account_locked": 423},
    "roles": [{"name": "user", "description": "Anyone registering or logging in"}],
    "routes": [
      {"method": "POST", "path": "/users", "summary": "Register a user",
       "request_fields": {"username": {"type": "string", "required": True, "min_length": 1},
                          "password": {"type": "string", "required": True, "min_length": 8}},
       "success_status": 201, "response_fields": ["id", "username"]},
      {"method": "POST", "path": "/login", "summary": "Log in; returns a session token",
       "request_fields": {"username": {"type": "string", "required": True},
                          "password": {"type": "string", "required": True}},
       "success_status": 200, "response_fields": ["username", "token"]}]},
  private={"gold_capabilities": caps("users", "login_attempts"),
           "state_machine": {"entity": "account", "states": ["active", "locked"], "initial": "active",
                             "terminal": [],
                             "transitions": [
                                 {"from": "active", "to": "locked", "action": "fifth_consecutive_failure", "roles": ["user"]},
                                 {"from": "locked", "to": "active", "action": "fifteen_minutes_pass", "roles": ["user"]}]}},
  checks='''
T0 = "2026-10-01T09:00:00+00:00"
PW = "correct-horse-1"


def _register(client, uid):
    name = uid("user")
    assert client.post("/users", json={"username": name, "password": PW}).status_code == 201
    return name


def _login(client, clock, name, password=PW, at=T0):
    return client.post("/login", json={"username": name, "password": password}, headers=clock(at))


def _fail(client, clock, name, times, at=T0):
    return [_login(client, clock, name, "wrong-password", at).status_code for _ in range(times)]


def test_register_never_returns_the_password(client, uid):
    """[safety] Registration is 201 and the response does not contain the password."""
    r = client.post("/users", json={"username": uid("u"), "password": PW})
    assert r.status_code == 201 and "password" not in r.json() and PW not in r.text


def test_correct_login_returns_a_token(client, clock, uid):
    """[functional] Correct credentials return 200 with a token and no password."""
    name = _register(client, uid)
    r = _login(client, clock, name)
    assert r.status_code == 200 and r.json().get("token") and PW not in r.text


def test_wrong_password_and_unknown_user_are_401(client, clock, uid):
    """[safety] A wrong password and an unknown username both return 401."""
    name = _register(client, uid)
    assert _login(client, clock, name, "nope-nope-nope").status_code == 401
    assert _login(client, clock, uid("ghost")).status_code == 401


def test_four_failures_do_not_lock(client, clock, uid):
    """[functional] After 4 failures the correct password still works."""
    name = _register(client, uid)
    assert _fail(client, clock, name, 4) == [401] * 4
    assert _login(client, clock, name).status_code == 200


def test_fifth_failure_locks_even_the_correct_password(client, clock, uid):
    """[safety] After 5 consecutive failures, the correct password returns 423."""
    name = _register(client, uid)
    assert _fail(client, clock, name, 5) == [401] * 5
    assert _login(client, clock, name).status_code == 423


def test_lock_still_holds_just_before_15_minutes(client, clock, uid):
    """[safety] 14 minutes 59 seconds after locking, login is still 423."""
    name = _register(client, uid)
    _fail(client, clock, name, 5)
    assert _login(client, clock, name, at="2026-10-01T09:14:59+00:00").status_code == 423


def test_lock_expires_after_15_minutes(client, clock, uid):
    """[functional] 15 minutes after locking, the correct password works again."""
    name = _register(client, uid)
    _fail(client, clock, name, 5)
    assert _login(client, clock, name, at="2026-10-01T09:15:01+00:00").status_code == 200


def test_success_resets_the_failure_count(client, clock, uid):
    """[functional] 4 failures, a success, then 4 more failures: still not locked."""
    name = _register(client, uid)
    _fail(client, clock, name, 4)
    assert _login(client, clock, name).status_code == 200
    _fail(client, clock, name, 4)
    assert _login(client, clock, name).status_code == 200


def test_lock_is_per_username(client, clock, uid):
    """[safety] Locking one account does not affect another."""
    locked, other = _register(client, uid), _register(client, uid)
    _fail(client, clock, locked, 5)
    assert _login(client, clock, other).status_code == 200


def test_duplicate_username_is_409(client, uid):
    """[safety] Registering an existing username is 409."""
    name = _register(client, uid)
    assert client.post("/users", json={"username": name, "password": PW}).status_code == 409


def test_short_password_is_422(client, uid):
    """[safety] A password shorter than 8 characters is rejected with 422."""
    assert client.post("/users", json={"username": uid("u"), "password": "short7!"}).status_code == 422


def test_unknown_fields_are_422(client, uid):
    """[safety] Extra registration fields such as role or is_admin are rejected with 422."""
    for field in ("role", "is_admin"):
        body = {"username": uid("u"), "password": PW, field: "admin"}
        assert client.post("/users", json=body).status_code == 422, field
''',
  reference='''
"""Reference implementation: login with lockout after 5 consecutive failures."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
''' + NOT_BLANK + CLOCK_FN + '''

app = FastAPI(title="Login lockout (reference)")
USERS: dict[str, dict] = {}
FAILURES: dict[str, int] = {}
LOCKED_UNTIL: dict[str, datetime] = {}
MAX_FAILURES = 5
LOCK = timedelta(minutes=15)


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1)
    password: str = Field(min_length=8)
    _check = field_validator("username")(_not_blank)


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str
    password: str


@app.post("/users", status_code=201)
def register(payload: RegisterIn) -> dict:
    if payload.username in USERS:
        raise HTTPException(409, "username taken")
    salt = secrets.token_bytes(16)
    USERS[payload.username] = {"id": uuid4().hex, "salt": salt, "hash": _hash(payload.password, salt)}
    return {"id": USERS[payload.username]["id"], "username": payload.username}


@app.post("/login")
def login(payload: LoginIn, x_clock_now: str | None = Header(None)) -> dict:
    now = _now(x_clock_now)
    name = payload.username
    until = LOCKED_UNTIL.get(name)
    if until and now < until:
        raise HTTPException(423, "account locked")
    if until and now >= until:
        del LOCKED_UNTIL[name]
    user = USERS.get(name)
    if user is None or not hmac.compare_digest(user["hash"], _hash(payload.password, user["salt"])):
        if user is not None:
            FAILURES[name] = FAILURES.get(name, 0) + 1
            if FAILURES[name] >= MAX_FAILURES:
                LOCKED_UNTIL[name] = now + LOCK
                FAILURES[name] = 0
        raise HTTPException(401, "invalid credentials")
    FAILURES[name] = 0
    return {"username": name, "token": secrets.token_urlsafe(24)}
''', notes="New task (Day 3) replacing SVAGA 3.0 rate_limit_login. Uses the x-clock-now test clock.")

# =================================================================== ticket lifecycle
TK_OUT = ["id", "requester_id", "title", "description", "status"]
write_task(
  task_id="ticket_lifecycle", title="Support ticket lifecycle", category="workflow_state", source="svaga3",
  prompt="""Create a support-ticket API. Customers open tickets. Agents start work on open tickets and resolve tickets
  that are in progress. The customer who opened a ticket may close it once it is resolved, or reopen a resolved
  ticket (back to in progress); agents may also reopen resolved tickets. Closed tickets can be reopened only by a
  manager. Actions by a role that is not allowed are 403; actions that do not fit the ticket's current status are
  409.""",
  interface={"framework": "fastapi", "auth": HEADERS, "status_codes": {**STATUS_A, "wrong_status_for_action": 409},
    "roles": [{"name": "customer", "description": "Opens tickets; closes or reopens their own resolved tickets"},
              {"name": "agent", "description": "Starts, resolves and reopens resolved tickets"},
              {"name": "manager", "description": "Reopens closed tickets"}],
    "routes": [
      {"method": "POST", "path": "/tickets", "summary": "Open a ticket (status open)", "roles": ["customer"],
       "request_fields": {"title": {"type": "string", "required": True, "min_length": 1},
                          "description": {"type": "string", "required": True, "min_length": 1}},
       "success_status": 201, "response_fields": TK_OUT},
      {"method": "GET", "path": "/tickets/{ticket_id}", "summary": "Read a ticket",
       "roles": ["customer", "agent", "manager"], "success_status": 200, "response_fields": TK_OUT},
      {"method": "POST", "path": "/tickets/{ticket_id}/start", "summary": "open -> in_progress",
       "roles": ["agent"], "success_status": 200, "response_fields": TK_OUT},
      {"method": "POST", "path": "/tickets/{ticket_id}/resolve", "summary": "in_progress -> resolved",
       "roles": ["agent"], "success_status": 200, "response_fields": TK_OUT},
      {"method": "POST", "path": "/tickets/{ticket_id}/close", "summary": "resolved -> closed (requesting customer only)",
       "roles": ["customer"], "success_status": 200, "response_fields": TK_OUT},
      {"method": "POST", "path": "/tickets/{ticket_id}/reopen",
       "summary": "resolved -> in_progress (requesting customer or agent); closed -> in_progress (manager only)",
       "roles": ["customer", "agent", "manager"], "success_status": 200, "response_fields": TK_OUT}]},
  private={"gold_capabilities": caps("tickets"),
           "state_machine": {"entity": "ticket", "states": ["open", "in_progress", "resolved", "closed"],
                             "initial": "open", "terminal": [],
                             "transitions": [
                                 {"from": "open", "to": "in_progress", "action": "start", "roles": ["agent"]},
                                 {"from": "in_progress", "to": "resolved", "action": "resolve", "roles": ["agent"]},
                                 {"from": "resolved", "to": "closed", "action": "close", "roles": ["customer"],
                                  "guard": "actor == requester"},
                                 {"from": "resolved", "to": "in_progress", "action": "reopen",
                                  "roles": ["customer", "agent"], "guard": "role == agent or actor == requester"},
                                 {"from": "closed", "to": "in_progress", "action": "reopen", "roles": ["manager"]}]}},
  checks='''
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
''',
  reference='''
"""Reference implementation: support ticket lifecycle."""
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
''' + NOT_BLANK + IDENTITY + '''

app = FastAPI(title="Ticket lifecycle (reference)")
TICKETS: dict[str, dict] = {}
ALL_ROLES = {"customer", "agent", "manager"}


class TicketIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    _check = field_validator("title", "description")(_not_blank)


def _get(ticket_id: str) -> dict:
    if ticket_id not in TICKETS:
        raise HTTPException(404, "ticket not found")
    return TICKETS[ticket_id]


def _move(ticket: dict, expected: str, new_status: str) -> dict:
    if ticket["status"] != expected:
        raise HTTPException(409, f"ticket must be {expected}")
    ticket["status"] = new_status
    return ticket


@app.post("/tickets", status_code=201)
def open_ticket(payload: TicketIn, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {"customer"})
    ticket = {"id": uuid4().hex, "requester_id": actor, **payload.model_dump(), "status": "open"}
    TICKETS[ticket["id"]] = ticket
    return ticket


@app.get("/tickets/{ticket_id}")
def read(ticket_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    _identity(x_actor_id, x_actor_role, ALL_ROLES)
    return _get(ticket_id)


@app.post("/tickets/{ticket_id}/start")
def start(ticket_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    _identity(x_actor_id, x_actor_role, {"agent"})
    return _move(_get(ticket_id), "open", "in_progress")


@app.post("/tickets/{ticket_id}/resolve")
def resolve(ticket_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    _identity(x_actor_id, x_actor_role, {"agent"})
    return _move(_get(ticket_id), "in_progress", "resolved")


@app.post("/tickets/{ticket_id}/close")
def close(ticket_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {"customer"})
    ticket = _get(ticket_id)
    if ticket["requester_id"] != actor:
        raise HTTPException(403, "only the requester can close")
    return _move(ticket, "resolved", "closed")


@app.post("/tickets/{ticket_id}/reopen")
def reopen(ticket_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, role = _identity(x_actor_id, x_actor_role, ALL_ROLES)
    ticket = _get(ticket_id)
    if ticket["status"] == "closed":
        if role != "manager":
            raise HTTPException(403, "only a manager can reopen a closed ticket")
        return _move(ticket, "closed", "in_progress")
    if role == "manager" or (role == "customer" and ticket["requester_id"] != actor):
        raise HTTPException(403, "not allowed to reopen")
    return _move(ticket, "resolved", "in_progress")
''', notes="New task (Day 3) replacing SVAGA 3.0 ticket_resolve.")
