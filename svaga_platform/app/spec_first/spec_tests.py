"""Turn a frozen BehaviorSpec plus the public interface into pytest code. No LLM is involved.

The generator works out a list of test cases (plain dicts) and writes them into one test file together with a small
runtime helper that builds valid request bodies, headers and entities. Each case becomes one parametrized test whose
id says what it checks, e.g. ``transition[POST /leave-requests/{request_id}/approve submitted->approved]``.

Things it deliberately skips (and records in ``skipped``): routes whose request body cannot be built from the
interface alone (a required array described only in words), and happy paths on tasks that call an outside service,
because the sandbox has no mock service.
"""
from __future__ import annotations

import json
from collections import deque
from typing import Any

from svaga_platform.app.spec_first.behavior_spec import BehaviorSpec, route_key

BUILDABLE = {"string", "integer", "number", "date", "datetime", "boolean", "object"}


def _routes(interface: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {route_key(r): r for r in interface.get("routes", [])}


def _buildable(route: dict[str, Any]) -> bool:
    for spec in (route.get("request_fields") or {}).values():
        if spec.get("required") and spec.get("type") not in BUILDABLE and not spec.get("enum"):
            return False
    return True


def _bad_numbers(fs: dict[str, Any]) -> list[Any]:
    out = []
    if fs.get("type") not in ("integer", "number"):
        return out
    if "minimum" in fs:
        out.append(fs["minimum"] - 1)
    if "exclusive_minimum" in fs:
        out.append(fs["exclusive_minimum"])
    if "maximum" in fs:
        out.append(fs["maximum"] + 1)
    return out


def build_cases(spec: BehaviorSpec, interface: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    routes = _routes(interface)
    codes = interface.get("status_codes") or {}
    auth = interface.get("auth") or {}
    headers_auth = auth.get("scheme") == "headers"
    external = bool(interface.get("mock_services"))
    all_roles = [r["name"] for r in interface.get("roles", [])]
    cases: list[dict[str, Any]] = []
    skipped: list[str] = []

    create_op = {}
    for op in spec.operations:
        r = routes.get(op.route)
        if op.kind == "create" and r and "id" in (r.get("response_fields") or []):
            if not _buildable(r):
                skipped.append(f"{op.route}: required field cannot be built from the interface; no entity tests")
            elif external:
                skipped.append(f"{op.route}: calls an outside service; no entity tests in the sandbox")
            else:
                create_op.setdefault(op.entity, op.route)

    def needs_entity(key: str) -> str | None:
        """Entity whose id fills this route's path, or None when the path has no id."""
        op = spec.op(key)
        if "{" not in key or op is None:
            return None
        return op.entity

    def can_target(key: str) -> bool:
        ent = needs_entity(key)
        return ent is None or ent in create_op

    for op in spec.operations:
        r = routes.get(op.route)
        if r is None:
            continue
        key = op.route
        fields = r.get("request_fields") or {}
        body_ok = _buildable(r)
        role = op.roles[0] if op.roles else None
        if fields and not body_ok:
            skipped.append(f"{key}: body not buildable; no validation tests")
        if fields and body_ok:
            base = {"route": key, "role": role, "entity": needs_entity(key) if can_target(key) else None}
            cases.append({**base, "kind": "extra_field", "expect": codes.get("unknown_body_field", 422)})
            for name, fs in fields.items():
                if fs.get("required"):
                    cases.append({**base, "kind": "missing_field", "field": name, "expect": codes.get("validation_error", 422)})
                if fs.get("type") == "string" and (fs.get("min_length") or 0) >= 1 and not fs.get("enum"):
                    cases.append({**base, "kind": "blank_field", "field": name, "expect": codes.get("validation_error", 422)})
                for bad in _bad_numbers(fs):
                    cases.append({**base, "kind": "bad_value", "field": name, "value": bad, "expect": codes.get("validation_error", 422)})
                if fs.get("enum"):
                    cases.append({**base, "kind": "bad_value", "field": name, "value": "not-a-listed-value",
                                  "expect": codes.get("validation_error", 422)})
            for rule in op.rules:
                if rule.kind == "field_order" and len(rule.fields) == 2 and rule.op:
                    cases.append({**base, "kind": "field_order", "fields": rule.fields, "op": rule.op, "expect": rule.error_status})
                if rule.kind == "unique" and op.kind == "create" and op.entity in create_op and rule.fields:
                    cases.append({**base, "kind": "unique", "field": rule.fields[0], "expect": rule.error_status})
        if op.kind == "create" and op.entity in create_op and create_op[op.entity] == key:
            cases.append({"route": key, "role": role, "kind": "create_ok", "expect": r.get("success_status", 201),
                          "response_fields": r.get("response_fields") or []})
        if "{" not in key:
            cases.append({"route": key, "role": None, "kind": "route_exists", "expect": "not 404/405"})
        if r["method"].upper() == "GET" and "{" not in key and r.get("response_fields") and not any(
                q.get("required") for q in (r.get("query_params") or {}).values()):
            ent = op.entity if op.entity in create_op else None
            cases.append({"route": key, "role": role, "kind": "list_shape", "entity": ent, "expect": 200})
        if op.kind == "read" and "{" in key and codes.get("not_found"):
            cases.append({"route": key, "role": role, "kind": "unknown_id", "expect": codes["not_found"]})
        if headers_auth and op.roles and can_target(key) and (body_ok or not fields):
            forbidden = codes.get("missing_or_wrong_identity", codes.get("forbidden", 403))
            allowed = set(op.roles) | {role for t in op.transitions for role in t.roles}
            ent = needs_entity(key)
            cases.append({"route": key, "role": None, "kind": "no_identity", "entity": ent, "expect": forbidden})
            others = [x for x in all_roles if x not in allowed]
            if others:
                cases.append({"route": key, "role": others[0], "kind": "wrong_role", "entity": ent,
                              "expect": codes.get("forbidden", 403)})

    # owner rules on routes that are not state moves (e.g. "only the booker can cancel")
    for op in spec.operations:
        if op.transitions or op.entity not in create_op or "{" not in op.route or not headers_auth or not op.roles:
            continue
        for rl in op.rules:
            if rl.kind in ("not_self", "owner_only"):
                bad_actor = "owner" if rl.kind == "not_self" else "other"
                cases.append({"kind": "actor_rule", "rule": rl.kind, "route": op.route, "from": "any", "entity": op.entity,
                              "setup": [], "step": {"route": op.route, "role": op.roles[0], "actor": bad_actor},
                              "expect": rl.error_status})

    # state machine cases
    for m in spec.state_machines:
        if m.entity not in create_op:
            skipped.append(f"state machine {m.entity}: entity cannot be created in the sandbox; no transition tests")
            continue
        edges = []
        for op in spec.operations:
            if op.entity != m.entity or op.kind == "create":  # create outcomes depend on the environment
                continue
            kinds = {rl.kind for rl in op.rules}
            actor = "owner" if "owner_only" in kinds else "other"
            for t in op.transitions:
                roles = t.roles or op.roles
                if not roles:
                    continue
                edges.append({"route": op.route, "from": t.from_state, "to": t.to_state, "role": roles[0], "actor": actor,
                              "rules": [rl.model_dump() for rl in op.rules]})
        # What a client sees right after create: the initial state, or the create call's own outcome. One outcome is
        # a fixed step (e.g. draft -> submitted); several depend on the environment, so no state is controllable.
        outcomes = sorted({t.to_state for o in spec.operations if o.entity == m.entity and o.kind == "create"
                           for t in o.transitions})
        after_create = outcomes or [m.initial]
        start = after_create if len(after_create) == 1 else []
        # shortest step list from the state after create to each state
        reach: dict[str, list[dict[str, Any]]] = {x: [] for x in start}
        queue = deque(start)
        while queue:
            s = queue.popleft()
            for e in edges:
                if e["from"] == s and e["to"] not in reach:
                    reach[e["to"]] = reach[s] + [{"route": e["route"], "role": e["role"], "actor": e["actor"]}]
                    queue.append(e["to"])
        read_route = next((o.route for o in spec.operations if o.entity == m.entity and o.kind == "read"), None)
        base = {"entity": m.entity, "status_field": m.field, "read_route": read_route}
        cases.append({**base, "kind": "initial_state", "state": after_create, "route": create_op[m.entity]})
        for e in edges:
            if e["from"] not in reach:
                continue
            step = {"route": e["route"], "role": e["role"], "actor": e["actor"]}
            cases.append({**base, "kind": "transition", "route": e["route"], "from": e["from"], "to": e["to"],
                          "setup": reach[e["from"]], "step": step})
            for rl in e["rules"]:
                if rl["kind"] in ("not_self", "owner_only"):
                    bad_actor = "owner" if rl["kind"] == "not_self" else "other"
                    cases.append({**base, "kind": "actor_rule", "rule": rl["kind"], "route": e["route"], "from": e["from"],
                                  "setup": reach[e["from"]], "step": {**step, "actor": bad_actor}, "expect": rl["error_status"]})
        conflict = codes.get("conflict")
        if conflict:
            action_ops = [o for o in spec.operations if o.entity == m.entity and o.transitions and o.kind != "create"]
            for state, setup in reach.items():
                for op in action_ops:
                    if any(t.from_state == state for t in op.transitions):
                        continue
                    kinds = {rl.kind for rl in op.rules}
                    roles = [r for t in op.transitions for r in (t.roles or op.roles)] or op.roles
                    if not roles:
                        continue
                    step = {"route": op.route, "role": roles[0], "actor": "owner" if "owner_only" in kinds else "other"}
                    cases.append({**base, "kind": "wrong_state", "route": op.route, "from": state, "setup": setup,
                                  "step": step, "expect": conflict})
    return cases, skipped


def _case_id(c: dict[str, Any]) -> str:
    k = c["kind"]
    if k in ("transition",):
        return f"transition[{c['route']} {c['from']}->{c['to']}]"
    if k in ("wrong_state", "actor_rule"):
        return f"{k}[{c['route']} from {c['from']}{' ' + c['rule'] if k == 'actor_rule' else ''}]"
    state = "|".join(c["state"]) if isinstance(c.get("state"), list) else c.get("state")
    extra = c.get("field") or ("/".join(c["fields"]) if c.get("fields") else "") or c.get("role") or state or ""
    if "value" in c:
        extra += f"={c['value']}"
    return f"{k}[{c['route']}{' ' + extra if extra else ''}]"


RUNTIME = r'''
import datetime as _dt
import random as _random
import re as _re
import uuid as _uuid

import pytest
from fastapi.testclient import TestClient

import app as app_module

client = TestClient(app_module.app)


def _hex():
    return _uuid.uuid4().hex[:10]


def H(role, actor=None):
    if AUTH.get("scheme") != "headers" or role is None:
        return {}
    return {AUTH["actor_header"]: actor or ("actor-" + _hex()), AUTH["role_header"]: role}


def _value(name, fs, i, ctx):
    t = fs.get("type")
    if fs.get("enum"):
        return fs["enum"][0]
    if t == "string":
        if fs.get("format") == "email" or "email" in name:
            return "t" + ctx["hex"] + str(i) + "@example.com"
        v = name.replace("_", " ") + " " + ctx["hex"]
        return v[: fs["max_length"]] if fs.get("max_length") else v
    if t in ("integer", "number"):
        if "minimum" in fs:
            v = fs["minimum"] if fs["minimum"] > 0 else 1
        elif "exclusive_minimum" in fs:
            v = fs["exclusive_minimum"] + 1
        else:
            v = 3
        if "maximum" in fs:
            v = min(v, fs["maximum"])
        return int(v) if t == "integer" else float(v)
    if t == "date":
        return (ctx["day"] + _dt.timedelta(days=i)).isoformat()
    if t == "datetime":
        return (ctx["at"] + _dt.timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if t == "boolean":
        return True
    if t == "object":
        return {"note": ctx["hex"]}
    return None


def _cmp(a, op, b):
    return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]


def make_body(route):
    fields = ROUTES[route].get("request_fields") or {}
    ctx = {"hex": _hex(), "day": _dt.date(2031, 1, 5) + _dt.timedelta(days=_random.randint(0, 3000)),
           "at": _dt.datetime(2031, 1, 5, 9, 0) + _dt.timedelta(days=_random.randint(0, 3000))}
    body = {}
    for i, (name, fs) in enumerate(fields.items()):
        if fs.get("required") or fs.get("type") in ("string", "integer", "number", "date", "datetime"):
            v = _value(name, fs, i, ctx)
            if v is not None:
                body[name] = v
    for left, op, right in ORDERS.get(route, []):
        if left in body and right in body and not _cmp(body[left], op, body[right]):
            body[left], body[right] = body[right], body[left]
    return body


def fill(route, ident):
    method, path = route.split(" ", 1)
    return method, _re.sub(r"\{[^}]+\}", str(ident), path, count=1)


def call(route, ident=None, body=None, headers=None):
    method, path = fill(route, ident if ident is not None else "999999999")
    kwargs = {"headers": headers or {}}
    if body is not None:
        kwargs["json"] = body
    return client.request(method, path, **kwargs)


def create(entity):
    route = CREATE[entity]
    owner = "owner-" + _hex()
    role = ROLES[route][0] if ROLES[route] else None
    r = call(route, body=make_body(route), headers=H(role, owner))
    assert r.status_code < 300, f"setup: create {entity} returned {r.status_code}: {r.text[:200]}"
    return r.json()["id"], owner


def fire(step, ident, owner):
    actor = owner if step["actor"] == "owner" else "other-" + _hex()
    fields = ROUTES[step["route"]].get("request_fields")
    return call(step["route"], ident, make_body(step["route"]) if fields else None, H(step["role"], actor))


def drive(steps, ident, owner):
    for s in steps:
        r = fire(s, ident, owner)
        assert r.status_code < 300, f"setup: {s['route']} returned {r.status_code}: {r.text[:200]}"


def status_of(case, ident, last):
    if case.get("read_route"):
        role = ROLES[case["read_route"]][0] if ROLES[case["read_route"]] else None
        r = call(case["read_route"], ident, headers=H(role, "reader-" + _hex()))
        if r.status_code == 200:
            return r.json().get(case["status_field"])
    return last.json().get(case["status_field"]) if last is not None else None


def run_case(c):
    kind = c["kind"]
    ident = None
    owner = None
    if c.get("entity") and kind not in ("initial_state",):
        ident, owner = create(c["entity"])
    hdr = H(c.get("role"), owner if kind != "wrong_role" else None)
    if kind == "create_ok":
        r = call(c["route"], body=make_body(c["route"]), headers=hdr)
        assert r.status_code == c["expect"], r.text[:300]
        missing = [f for f in c["response_fields"] if f not in r.json()]
        assert not missing, f"response is missing fields {missing}"
        return
    if kind in ("extra_field", "missing_field", "blank_field", "bad_value", "field_order", "unique"):
        body = make_body(c["route"])
        if kind == "extra_field":
            body["svaga_unexpected_field"] = "x"
        elif kind == "missing_field":
            body.pop(c["field"], None)
        elif kind == "blank_field":
            body[c["field"]] = "   "
        elif kind == "bad_value":
            body[c["field"]] = c["value"]
        elif kind == "field_order":
            left, right = c["fields"]
            body[left], body[right] = body[right], body[left]
            if body[left] == body[right] or _cmp(body[left], c["op"], body[right]):
                pytest.skip("could not build a violating pair")
        elif kind == "unique":
            first = call(c["route"], body=body, headers=hdr)
            assert first.status_code < 300, first.text[:300]
            again = make_body(c["route"])
            again[c["field"]] = body[c["field"]]
            body = again
        r = call(c["route"], ident, body, hdr)
        assert r.status_code == c["expect"], f"expected {c['expect']}, got {r.status_code}: {r.text[:300]}"
        return
    if kind == "route_exists":
        r = call(c["route"])
        assert r.status_code not in (404, 405), f"route missing: {c['route']} returned {r.status_code}"
        return
    if kind == "list_shape":
        r = call(c["route"], headers=H(c.get("role"), "reader-" + _hex()))
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert isinstance(body, list), f"list route must return a bare JSON array, got {type(body).__name__}"
        if ident is not None and AUTH.get("scheme") != "headers":  # with identities, lists may be scoped per caller
            assert ident in [x.get("id") for x in body if isinstance(x, dict)], "created record is not in the list"
        return
    if kind == "unknown_id":
        r = call(c["route"], "999999999", headers=hdr)
        assert r.status_code == c["expect"], r.text[:300]
        return
    if kind in ("no_identity", "wrong_role"):
        fields = ROUTES[c["route"]].get("request_fields")
        r = call(c["route"], ident, make_body(c["route"]) if fields else None, {} if kind == "no_identity" else hdr)
        assert r.status_code == c["expect"], f"expected {c['expect']}, got {r.status_code}: {r.text[:300]}"
        return
    if kind == "initial_state":
        ident, owner = create(c["entity"])
        states = c["state"] if isinstance(c["state"], list) else [c["state"]]
        assert status_of(c, ident, None) in states, f"status after create is not one of {states}"
        return
    drive(c["setup"], ident, owner)
    r = fire(c["step"], ident, owner)
    if kind == "transition":
        assert r.status_code < 300, f"expected success, got {r.status_code}: {r.text[:300]}"
        assert status_of(c, ident, r) == c["to"]
    else:
        assert r.status_code == c["expect"], f"expected {c['expect']}, got {r.status_code}: {r.text[:300]}"


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_spec(case):
    run_case(case)
'''


def generate_spec_tests(spec: BehaviorSpec, interface: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return (pytest source, summary). The summary lists case counts by kind and what was skipped."""
    cases, skipped = build_cases(spec, interface)
    routes = _routes(interface)
    create = {}
    for op in spec.operations:
        if op.kind == "create" and op.entity not in create:
            create[op.entity] = op.route
    orders = {op.route: [[r.fields[0], r.op, r.fields[1]] for r in op.rules if r.kind == "field_order" and len(r.fields) == 2 and r.op]
              for op in spec.operations}
    roles = {op.route: op.roles for op in spec.operations}
    auth = interface.get("auth") or {}
    header = (
        '"""Tests generated from the frozen BehaviorSpec by SVAGA M2 (no LLM wrote these).\n\n'
        f'spec_hash: {spec.spec_hash()}\n"""\n'
        f"import json as _json\n\nAUTH = _json.loads({json.dumps(json.dumps(auth))})\n"
        f"ROUTES = _json.loads({json.dumps(json.dumps(routes))})\n"
        f"ROLES = _json.loads({json.dumps(json.dumps(roles))})\n"
        f"CREATE = _json.loads({json.dumps(json.dumps(create))})\n"
        f"ORDERS = _json.loads({json.dumps(json.dumps(orders))})\n"
        f"CASES = _json.loads({json.dumps(json.dumps(cases))})\n"
        f"IDS = {json.dumps([_case_id(c) for c in cases])}\n"
    )
    counts: dict[str, int] = {}
    for c in cases:
        counts[c["kind"]] = counts.get(c["kind"], 0) + 1
    return header + RUNTIME, {"cases": len(cases), "by_kind": counts, "skipped": skipped}
