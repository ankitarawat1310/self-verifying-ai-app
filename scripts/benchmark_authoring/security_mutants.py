"""Hand-written security bugs (B10): three per task, modeled on mistakes code generators commonly make.

Each bug is one or more exact text edits to the task's reference app (find -> replace, optional occurrence), plus the
hidden check(s) expected to catch it. `python security_mutants.py` writes mutants/security.yaml for every task;
`python scripts/build_security_mutants.py` applies them and verifies each is caught.
"""
from pathlib import Path

import yaml

from common import ROOT

SELF_APPROVAL = ('    if record["requester_id"] == actor:\n        raise HTTPException(403, "requesters cannot decide their own request")\n', "")
TERMINAL = ('    if record["status"] != "submitted":\n        raise HTTPException(409, "request already decided")\n', "")


def bug(id, description, edits, expected):
    return {"id": id, "description": description,
            "edits": [{"find": e[0], "replace": e[1], "occurrence": e[2] if len(e) > 2 else 1} for e in edits],
            "expected_failing_checks": expected}


BUGS = {
  "crud_contact_directory": [
    bug("sec_email_case_sensitive", "Email uniqueness compares case-sensitively, so ADA@X and ada@X both exist",
        [('c["email"].lower() == email.lower()', 'c["email"] == email')], ["test_duplicate_email_ignoring_case_is_409"]),
    bug("sec_patch_skips_uniqueness", "PATCH does not re-check email uniqueness",
        [('    if "email" in changes and _email_taken(changes["email"], exclude=contact_id):\n        raise HTTPException(409, "email already exists")\n', "")],
        ["test_update_cannot_take_another_contacts_email"]),
    bug("sec_mass_assignment", "Create accepts and stores undeclared fields such as admin",
        [('    model_config = ConfigDict(extra="forbid")', '    model_config = ConfigDict(extra="allow")', 1)],
        ["test_unknown_fields_are_rejected"])],
  "crud_inventory_tracker": [
    bug("sec_patch_negative_stock", "PATCH drops the nonnegative stock rule",
        [('    stock: StrictInt | None = Field(default=None, ge=0)', '    stock: StrictInt | None = None')],
        ["test_patch_to_negative_stock_is_rejected_and_unchanged"]),
    bug("sec_sku_case_sensitive", "SKU uniqueness compares case-sensitively",
        [('i["sku"].lower() == payload.sku.lower()', 'i["sku"] == payload.sku')], ["test_duplicate_sku_ignoring_case_is_409"]),
    bug("sec_sku_changeable", "PATCH lets clients change the SKU of an existing item",
        [('    name: str | None = Field(default=None, min_length=1)\n', '    name: str | None = Field(default=None, min_length=1)\n    sku: str | None = None\n')],
        ["test_sku_cannot_be_changed"])],
  "crud_appointment_registry": [
    bug("sec_patch_skips_time_rule", "PATCH does not re-validate end after start",
        [('    if merged["end_at"] <= merged["start_at"]:\n        raise HTTPException(422, "end_at must be after start_at")\n', "")],
        ["test_partial_update_cannot_break_the_time_rule"]),
    bug("sec_zero_length_allowed", "Create accepts an end equal to the start",
        [('        if self.end_at <= self.start_at:', '        if self.end_at < self.start_at:')], ["test_end_equal_to_start_is_422"]),
    bug("sec_code_changeable", "PATCH lets clients change the unique appointment code",
        [('    title: str | None = Field(default=None, min_length=1)\n', '    title: str | None = Field(default=None, min_length=1)\n    code: str | None = None\n')],
        ["test_unknown_fields_are_rejected"])],
  "crud_profile_mass_assignment": [
    bug("sec_role_on_create", "Create accepts a role field (privilege escalation at sign-up)",
        [('    display_name: str = Field(min_length=1)\n', '    display_name: str = Field(min_length=1)\n    role: str | bool = "member"\n')],
        ["test_privileged_fields_on_create_are_rejected"]),
    bug("sec_patch_ignores_unknown", "PATCH silently ignores unknown fields instead of rejecting them",
        [('    model_config = ConfigDict(extra="forbid")', '    model_config = ConfigDict(extra="ignore")', 2)],
        ["test_privileged_patch_is_rejected_without_state_change"]),
    bug("sec_patch_skips_uniqueness", "PATCH does not re-check username uniqueness",
        [('    if "username" in changes and _username_taken(changes["username"], exclude=profile_id):\n        raise HTTPException(409, "username already exists")\n', "")],
        ["test_duplicate_username_is_409"])],
  "approval_leave_request": [
    bug("sec_self_approval", "Requesters can approve their own leave", [SELF_APPROVAL],
        ["test_requester_cannot_self_approve_even_as_manager"]),
    bug("sec_terminal_mutable", "Approved or rejected requests can be decided again", [TERMINAL],
        ["test_terminal_decisions_cannot_change"]),
    bug("sec_employee_can_approve", "The employee role is allowed to approve",
        [('    actor, _ = _identity(x_actor_id, x_actor_role, {"manager"})\n    return _decide(request_id, actor, "approved")',
          '    actor, _ = _identity(x_actor_id, x_actor_role, {"manager", "employee"})\n    return _decide(request_id, actor, "approved")')],
        ["test_employee_role_cannot_decide"])],
  "approval_expense_request": [
    bug("sec_self_approval", "Requesters can approve their own expense", [SELF_APPROVAL],
        ["test_requester_cannot_self_approve_even_as_manager"]),
    bug("sec_terminal_mutable", "Decided requests can be decided again", [TERMINAL],
        ["test_terminal_decisions_cannot_change", "test_approval_is_not_repeatable"]),
    bug("sec_employee_can_approve", "The employee role is allowed to approve",
        [('    actor, _ = _identity(x_actor_id, x_actor_role, {"manager"})\n    return _decide(request_id, actor, "approved")',
          '    actor, _ = _identity(x_actor_id, x_actor_role, {"manager", "employee"})\n    return _decide(request_id, actor, "approved")')],
        ["test_employee_cannot_approve_or_reject"])],
  "approval_purchase_request": [
    bug("sec_reject_skips_limit", "Managers can reject high-value requests (limit applied only to approve)",
        [('    return _decide_with_limit(request_id, actor, role, "rejected")', '    return _decide(request_id, actor, "rejected")')],
        ["test_manager_cannot_decide_above_5000"]),
    bug("sec_status_injection", "Unknown submit fields such as status are silently accepted",
        [('    model_config = ConfigDict(extra="forbid")', '    model_config = ConfigDict(extra="ignore")')],
        ["test_status_injection_is_422"]),
    bug("sec_wrong_limit", "Manager limit doubled to 10000",
        [('record["amount"] > MANAGER_LIMIT:', 'record["amount"] > MANAGER_LIMIT * 2:')],
        ["test_manager_cannot_decide_above_5000"])],
  "approval_emergency_access": [
    bug("sec_no_upper_bound", "Duration has no 8-hour maximum",
        [('    duration_hours: StrictInt = Field(ge=1, le=8)', '    duration_hours: StrictInt = Field(ge=1)')],
        ["test_duration_outside_1_to_8_is_422"]),
    bug("sec_auto_approve_honored", "A caller-supplied auto_approve flag approves the request immediately",
        [('    duration_hours: StrictInt = Field(ge=1, le=8)\n', '    duration_hours: StrictInt = Field(ge=1, le=8)\n    auto_approve: bool = False\n'),
         ('    actor, _ = _identity(x_actor_id, x_actor_role, {"user"})\n    return _submit(actor, payload.model_dump())',
          '    actor, _ = _identity(x_actor_id, x_actor_role, {"user"})\n    record = _submit(actor, payload.model_dump(exclude={"auto_approve"}))\n    if payload.auto_approve:\n        record["status"] = "approved"\n    return record')],
        ["test_bypass_fields_are_rejected"]),
    bug("sec_self_approval", "Requesters can approve their own access", [SELF_APPROVAL],
        ["test_requester_cannot_self_approve"])],
  "billing_invoice": [
    bug("sec_client_total_trusted", "A client-supplied total overrides the computed one",
        [('    line_items: list[LineIn] = Field(min_length=1)\n', '    line_items: list[LineIn] = Field(min_length=1)\n    total: float | None = None\n'),
         ('"total": _total(lines),', '"total": payload.total if payload.total is not None else _total(lines),')],
        ["test_client_cannot_set_total_or_status"]),
    bug("sec_any_payment_accepted", "Any payment amount marks the invoice paid",
        [('        raise HTTPException(422, "amount must equal the invoice total")', '        pass')],
        ["test_wrong_payment_amount_is_422_and_unpaid"]),
    bug("sec_float_totals", "Totals use raw floating point instead of rounding to cents",
        [('    return float(Decimal(total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))',
          '    return float(sum(l["quantity"] * l["unit_price"] for l in lines))')],
        ["test_total_is_rounded_to_cents"])],
  "role_scoped_documents": [
    bug("sec_bola_read", "Reading by id does not check ownership (broken object-level authorization)",
        [('    actor, role = _identity(x_actor_id, x_actor_role, ROLES)\n    return _visible(document_id, actor, role)',
          '    _identity(x_actor_id, x_actor_role, ROLES)\n    if document_id not in DOCUMENTS:\n        raise HTTPException(404, "document not found")\n    return DOCUMENTS[document_id]')],
        ["test_reading_another_users_document_is_404"]),
    bug("sec_list_all_param", "?all=true returns every document to any user",
        [('def list_documents(x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> list[dict]:\n    actor, role = _identity(x_actor_id, x_actor_role, ROLES)\n    return [d for d in DOCUMENTS.values() if role == "admin" or d["owner_id"] == actor]',
          'def list_documents(all: bool = False, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> list[dict]:\n    actor, role = _identity(x_actor_id, x_actor_role, ROLES)\n    return [d for d in DOCUMENTS.values() if all or role == "admin" or d["owner_id"] == actor]')],
        ["test_query_parameters_cannot_widen_the_list"]),
    bug("sec_owner_from_body", "A client-supplied owner_id is trusted on create",
        [('    body: str\n', '    body: str\n    owner_id: str | None = None\n'),
         ('    doc = {"id": uuid4().hex, "owner_id": actor, **payload.model_dump()}',
          '    data = payload.model_dump()\n    owner = data.pop("owner_id") or actor\n    doc = {"id": uuid4().hex, "owner_id": owner, **data}')],
        ["test_owner_cannot_be_supplied_or_changed"])],
  "login_lockout": [
    bug("sec_lock_after_10", "Lockout threshold is 10 instead of 5", [("MAX_FAILURES = 5", "MAX_FAILURES = 10")],
        ["test_fifth_failure_locks_even_the_correct_password"]),
    bug("sec_user_enumeration", "Unknown usernames return 404, revealing which accounts exist",
        [('    user = USERS.get(name)\n', '    user = USERS.get(name)\n    if user is None:\n        raise HTTPException(404, "no such user")\n')],
        ["test_wrong_password_and_unknown_user_are_401"]),
    bug("sec_password_echo", "Registration echoes the password back",
        [('    return {"id": USERS[payload.username]["id"], "username": payload.username}',
          '    return {"id": USERS[payload.username]["id"], "username": payload.username, "password": payload.password}')],
        ["test_register_never_returns_the_password"])],
  "password_reset_token": [
    bug("sec_token_reusable", "Tokens are not marked used after a reset",
        [('    record["valid"] = False\n    _set_password(USERS[record["email"]], payload.new_password)',
          '    _set_password(USERS[record["email"]], payload.new_password)')],
        ["test_token_works_only_once"]),
    bug("sec_no_expiry", "Tokens never expire",
        [('if record is None or not record["valid"] or now >= record["expires"]:', 'if record is None or not record["valid"]:')],
        ["test_token_expires_after_60_minutes"]),
    bug("sec_account_enumeration", "Reset requests for unknown emails return 404",
        [('    if payload.email in USERS:\n        for record', '    if payload.email not in USERS:\n        raise HTTPException(404, "unknown email")\n    if payload.email in USERS:\n        for record')],
        ["test_request_does_not_reveal_accounts"])],
  "room_booking": [
    bug("sec_anyone_cancels", "Any employee can cancel anyone's booking",
        [('    if booking["booked_by"] != actor:\n        raise HTTPException(403, "only the booker can cancel")\n', "")],
        ["test_only_the_booker_can_cancel"]),
    bug("sec_no_max_length", "The 4-hour limit is not enforced",
        [('    if payload.end_at - payload.start_at > MAX_LENGTH:\n        raise HTTPException(422, "bookings last at most 4 hours")\n', "")],
        ["test_four_hour_limit"]),
    bug("sec_naive_overlap", "Overlap test only checks whether the new start falls inside an existing booking",
        [('payload.start_at < other["end_at"] and other["start_at"] < payload.end_at:',
          'other["start_at"] <= payload.start_at < other["end_at"]:')],
        ["test_overlapping_bookings_are_409"])],
  "task_dependencies": [
    bug("sec_no_cycle_check", "Adding a dependency never checks for cycles",
        [('    if _reaches(payload.task_id, task_id):\n        raise HTTPException(409, "dependency would create a cycle")\n', "")],
        ["test_two_task_cycle_is_409", "test_longer_cycle_is_409"]),
    bug("sec_complete_ignores_deps", "Tasks complete even when dependencies are unfinished",
        [('    if any(TASKS[d]["status"] != "done" for d in task["depends_on"]):\n        raise HTTPException(409, "dependencies not done")\n', "")],
        ["test_blocked_until_dependency_is_done"]),
    bug("sec_dependency_on_done_task", "Dependencies can be added to a task that is already done",
        [('    if task["status"] == "done":\n        raise HTTPException(409, "task already done")\n    if _reaches(', '    if _reaches(')],
        ["test_no_new_dependencies_on_a_done_task"])],
  "ticket_lifecycle": [
    bug("sec_any_customer_closes", "Any customer can close someone else's ticket",
        [('    if ticket["requester_id"] != actor:\n        raise HTTPException(403, "only the requester can close")\n', "")],
        ["test_other_customer_cannot_close"]),
    bug("sec_customer_reopens_closed", "Customers can reopen closed tickets without a manager",
        [('        if role != "manager":\n            raise HTTPException(403, "only a manager can reopen a closed ticket")',
          '        if role not in {"manager", "customer"}:\n            raise HTTPException(403, "only a manager can reopen a closed ticket")')],
        ["test_closed_ticket_cannot_be_reopened_without_manager"]),
    bug("sec_customer_resolves", "Customers can resolve tickets",
        [('    _identity(x_actor_id, x_actor_role, {"agent"})\n    return _move(_get(ticket_id), "in_progress", "resolved")',
          '    _identity(x_actor_id, x_actor_role, {"agent", "customer"})\n    return _move(_get(ticket_id), "in_progress", "resolved")')],
        ["test_customer_cannot_resolve_or_start"])],
  "webhook_dispatcher": [
    bug("sec_five_attempts", "Retries 5 times instead of 3", [("MAX_ATTEMPTS = 3", "MAX_ATTEMPTS = 5")],
        ["test_gives_up_after_three_attempts"]),
    bug("sec_4xx_is_success", "Any answer below 500 counts as delivered",
        [("if 200 <= reply.status_code < 300:", "if reply.status_code < 500:")],
        ["test_client_error_status_also_counts_as_failure"]),
    bug("sec_ignores_unknown_fields", "Caller-supplied url/status/max_attempts are silently ignored instead of rejected",
        [('    model_config = ConfigDict(extra="forbid")', '    model_config = ConfigDict(extra="ignore")')],
        ["test_caller_cannot_choose_url_status_or_attempts"])],
  "connector_shipping_quote": [
    bug("sec_endpoint_override", "A caller-supplied endpoint replaces the declared connector (SSRF)",
        [('    weight: float = Field(gt=0, le=100)\n', '    weight: float = Field(gt=0, le=100)\n    endpoint: str | None = None\n'),
         ('reply = httpx.post(CONNECTOR_URL, json=payload.model_dump(), timeout=5.0)',
          'reply = httpx.post(payload.endpoint or CONNECTOR_URL, json=payload.model_dump(exclude={"endpoint"}), timeout=5.0)')],
        ["test_endpoint_override_is_rejected_before_any_call"]),
    bug("sec_fail_open", "Connector failure stores a zero-price quote instead of returning 502",
        [('        raise HTTPException(502, "shipping connector failed") from error', '        price = 0.0')],
        ["test_connector_error_is_502_and_not_stored"]),
    bug("sec_unvalidated_price", "The connector's price is stored without type checking",
        [('    if isinstance(price, bool) or not isinstance(price, (int, float)):\n        raise HTTPException(502, "invalid price from connector")\n', ""),
         ('"price": float(price)', '"price": price')],
        ["test_non_numeric_price_is_502"])],
  "connector_weather_lookup": [
    bug("sec_endpoint_override", "A caller-supplied endpoint replaces the declared connector (SSRF)",
        [('    location: str = Field(min_length=1)\n', '    location: str = Field(min_length=1)\n    endpoint: str | None = None\n'),
         ('reply = httpx.get(CONNECTOR_URL, params=', 'reply = httpx.get(payload.endpoint or CONNECTOR_URL, params=')],
        ["test_endpoint_override_is_rejected_before_any_call"]),
    bug("sec_default_condition", "A missing condition is filled in as Unknown instead of failing",
        [('data["temperature"], data["condition"]', 'data["temperature"], data.get("condition", "Unknown")')],
        ["test_missing_condition_is_502_and_not_stored"]),
    bug("sec_blank_condition", "A blank condition is accepted",
        [('    if not isinstance(condition, str) or not condition.strip():', '    if not isinstance(condition, str):')],
        ["test_blank_condition_is_502"])],
  "connector_address_validation": [
    bug("sec_method_override", "A caller-supplied HTTP method is used for the connector call",
        [('    address: str = Field(min_length=1)\n', '    address: str = Field(min_length=1)\n    method: str = "POST"\n'),
         ('reply = httpx.post(CONNECTOR_URL, json={"address": payload.address}, timeout=5.0)',
          'reply = httpx.request(payload.method, CONNECTOR_URL, json={"address": payload.address}, timeout=5.0)')],
        ["test_endpoint_or_method_override_is_rejected"]),
    bug("sec_unvalidated_flag", "The valid flag is stored without checking it is a boolean",
        [('    if not isinstance(valid, bool) or not isinstance(normalized, str) or not normalized.strip():',
          '    if not isinstance(normalized, str) or not normalized.strip():')],
        ["test_non_boolean_valid_flag_is_502"]),
    bug("sec_fail_open", "Connector failure stores the address as invalid instead of returning 502",
        [('        raise HTTPException(502, "address connector failed") from error', '        normalized, valid = payload.address, False')],
        ["test_connector_error_is_502"])],
  "connector_document_delivery": [
    bug("sec_forward_authorization", "The caller's Authorization header is forwarded to the connector",
        [('from fastapi import FastAPI, HTTPException', 'from fastapi import FastAPI, Header, HTTPException'),
         ('def deliver(payload: DeliveryIn) -> dict:', 'def deliver(payload: DeliveryIn, authorization: str | None = Header(None)) -> dict:'),
         ('reply = httpx.post(CONNECTOR_URL, json=payload.model_dump(), timeout=5.0)',
          'reply = httpx.post(CONNECTOR_URL, json=payload.model_dump(), timeout=5.0, headers={"Authorization": authorization} if authorization else None)')],
        ["test_caller_authorization_header_is_not_forwarded"]),
    bug("sec_any_status", "Any status from the connector is stored",
        [('if not isinstance(delivery_id, str) or not delivery_id.strip() or status not in ALLOWED_STATUS:',
          'if not isinstance(delivery_id, str) or not delivery_id.strip():')],
        ["test_unexpected_status_is_502_and_not_stored"]),
    bug("sec_callback_forwarded", "A caller-supplied callback_url is accepted and forwarded",
        [('    recipient: str = Field(min_length=1)\n', '    recipient: str = Field(min_length=1)\n    callback_url: str | None = None\n')],
        ["test_injected_fields_are_rejected_before_any_call"])],
}


if __name__ == "__main__":
    for task_id, bugs in BUGS.items():
        path = ROOT / "benchmarks/private" / task_id / "mutants" / "security.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(yaml.safe_dump({"task_id": task_id, "security_mutants": bugs}, sort_keys=False, width=200,
                                        allow_unicode=True).replace("\n", "\r\n").encode("utf-8"))
        print(f"wrote {len(bugs)} security bugs for {task_id}")
