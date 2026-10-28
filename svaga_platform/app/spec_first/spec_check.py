"""Check a BehaviorSpec before code is written.

Two layers:
1. ``validate_spec``: structural checks against the public interface (every route covered once, known roles,
   known states and fields).
2. ``model_check``: a small bounded model checker. For each state machine it explores every sequence of
   operations up to ``depth`` steps from the initial state, with abstract actors (the owner and a non-owner for
   each role), and checks: every state reachable, terminal states have no way out, no dead-end non-terminal
   state, each operation deterministic, and every transition fireable by someone under the spec's own rules.
Each problem comes back as a plain sentence (plus a trace for the model checker) that is fed to the LLM to fix.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from svaga_platform.app.spec_first.behavior_spec import BehaviorSpec, Operation, route_key


@dataclass
class SpecReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    traces: list[dict[str, Any]] = field(default_factory=list)
    explored_paths: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings, "traces": self.traces,
                "explored_paths": self.explored_paths}


def _routes(interface: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {route_key(r): r for r in interface.get("routes", [])}


def _entity_fields(interface: dict[str, Any], spec: BehaviorSpec, entity: str) -> set[str]:
    names: set[str] = set()
    routes = _routes(interface)
    for op in spec.operations:
        if op.entity == entity and op.route in routes:
            r = routes[op.route]
            names.update((r.get("request_fields") or {}).keys())
            names.update(r.get("response_fields") or [])
    return names


ORDERED_TYPES = {"date": "date", "datetime": "datetime", "integer": "number", "number": "number"}
OWNER_RULES = ("not_self", "owner_only")


def rule_problem(rule, op: Operation, interface: dict[str, Any], spec: BehaviorSpec) -> str | None:
    """Why this rule cannot be right for this route (None if it is fine). Shared by the validator and normalize()."""
    route = _routes(interface).get(op.route, {})
    req = route.get("request_fields") or {}
    if rule.kind == "field_order":
        if len(rule.fields) != 2 or rule.op is None:
            return "field_order rule needs two fields and an op"
        if not set(rule.fields) <= set(req):
            return f"field_order fields {rule.fields} are not request fields of this route"
        kinds = {ORDERED_TYPES.get(req[f].get("type")) for f in rule.fields}
        if None in kinds or len(kinds) != 1:
            return (f"field_order compares two dates, two datetimes or two numbers; {rule.fields} are "
                    f"{[req[f].get('type') for f in rule.fields]} (single-field limits are already in the interface)")
    elif rule.kind in OWNER_RULES:
        if op.kind == "create":
            return f"{rule.kind} cannot apply to create: the record and its owner do not exist yet"
        if (interface.get("auth") or {}).get("scheme") != "headers":
            return f"{rule.kind} needs caller identity, but this interface has no identity headers"
        if len(rule.fields) != 1:
            return f"{rule.kind} rule needs exactly one owner field"
        if rule.fields[0] == "id":
            return f"{rule.kind} owner field must hold the owner's actor id, not the record id"
        if rule.fields[0] not in _entity_fields(interface, spec, op.entity):
            return f"owner field '{rule.fields[0]}' is not a field of {op.entity}"
    elif rule.kind == "unique" and len(rule.fields) != 1:
        return "unique rule needs exactly one field"
    if not 400 <= rule.error_status < 500:
        return f"rule error_status {rule.error_status} is not a 4xx code"
    return None


_STARTS = {"start", "begin", "from", "opens", "check_in"}
_ENDS = {"end", "finish", "until", "closes", "check_out", "due"}


def _reversed_range(rule) -> bool:
    """field_order that requires a start-like field to come AFTER an end-like field (e.g. start_at > end_at)."""
    def kind(name: str) -> str | None:
        parts = set(name.lower().split("_"))
        return "start" if parts & _STARTS else "end" if parts & _ENDS else None

    left, right = (kind(f) for f in rule.fields)
    return (left, right) == ("start", "end") and rule.op in (">", ">=") or \
        (left, right) == ("end", "start") and rule.op in ("<", "<=")


def validate_spec(spec: BehaviorSpec, interface: dict[str, Any]) -> SpecReport:
    errors: list[str] = []
    warnings: list[str] = []
    routes = _routes(interface)
    roles = {r["name"] for r in interface.get("roles", [])}
    seen: dict[str, int] = {}
    for op in spec.operations:
        seen[op.route] = seen.get(op.route, 0) + 1
    for key in routes:
        if seen.get(key, 0) == 0:
            errors.append(f"route {key} from the interface has no operation in the spec")
    for key, n in seen.items():
        if key not in routes:
            errors.append(f"operation {key} is not a route in the interface")
        elif n > 1:
            errors.append(f"route {key} appears {n} times; list each route once")

    machines = {m.entity: m for m in spec.state_machines}
    for m in spec.state_machines:
        if m.initial not in m.states:
            errors.append(f"state machine {m.entity}: initial state '{m.initial}' is not in states {m.states}")
        for t in m.terminal:
            if t not in m.states:
                errors.append(f"state machine {m.entity}: terminal state '{t}' is not in states")
        if not any(o.kind == "create" and o.entity == m.entity for o in spec.operations):
            errors.append(f"state machine {m.entity}: no create operation for this entity")
        fields = _entity_fields(interface, spec, m.entity)
        if fields and m.field not in fields:
            warnings.append(f"state machine {m.entity}: field '{m.field}' is not a response field of its routes")

    status_values = {int(v) for v in (interface.get("status_codes") or {}).values() if str(v).isdigit()}
    for op in spec.operations:
        for role in op.roles:
            if roles and role not in roles:
                errors.append(f"{op.route}: role '{role}' is not declared in the interface")
        if op.transitions:
            m = machines.get(op.entity)
            if m is None:
                errors.append(f"{op.route}: has transitions but entity '{op.entity}' has no state machine")
            else:
                for t in op.transitions:
                    for s in (t.from_state, t.to_state):
                        if s not in m.states:
                            errors.append(f"{op.route}: state '{s}' is not in {op.entity} states {m.states}")
                    for role in t.roles:
                        if role not in (op.roles or roles):
                            errors.append(f"{op.route}: transition role '{role}' is not allowed on this route")
        for rule in op.rules:
            problem = rule_problem(rule, op, interface, spec)
            if problem:
                errors.append(f"{op.route}: {problem}")
            elif rule.kind == "field_order" and _reversed_range(rule):
                left, right = rule.fields
                errors.append(f"{op.route}: field_order says {left} {rule.op} {right}, which puts the end before the "
                              f"start; the rule must say what is REQUIRED, e.g. [start, end] with '<'")
            elif status_values and rule.error_status not in status_values:
                warnings.append(f"{op.route}: rule error_status {rule.error_status} is not in the interface status codes")
    return SpecReport(ok=not errors, errors=errors, warnings=warnings)


def _fire_options(op: Operation, t) -> list[tuple[str, str]]:
    """Abstract (actor, role) pairs that may fire transition t: actor is 'owner' or 'other'."""
    roles = t.roles or op.roles or ["*"]
    kinds = {r.kind for r in op.rules}
    options = []
    for role in roles:
        for actor in ("owner", "other"):
            if "not_self" in kinds and actor == "owner":
                continue
            if "owner_only" in kinds and actor == "other":
                continue
            options.append((actor, role))
    return options


def model_check(spec: BehaviorSpec, depth: int = 6) -> SpecReport:
    errors: list[str] = []
    warnings: list[str] = []
    traces: list[dict[str, Any]] = []
    explored = 0
    for m in spec.state_machines:
        if m.initial not in m.states:
            continue
        edges: list[tuple[str, str, str, list[tuple[str, str]]]] = []  # from, to, route, who
        for op in spec.operations:
            if op.entity != m.entity:
                continue
            seen_from: dict[str, str] = {}
            for t in op.transitions:
                if op.kind == "create":
                    # outcome of the create call itself (e.g. an outside service answered): several are allowed
                    if t.from_state != m.initial:
                        errors.append(f"{op.route}: a create outcome must start at the initial state '{m.initial}'")
                    edges.append((t.from_state, t.to_state, op.route, [("owner", r) for r in (t.roles or op.roles or ["*"])]))
                    continue
                if t.from_state in seen_from and seen_from[t.from_state] != t.to_state:
                    errors.append(f"{op.route}: not deterministic, from '{t.from_state}' it goes to both "
                                  f"'{seen_from[t.from_state]}' and '{t.to_state}'")
                seen_from[t.from_state] = t.to_state
                who = _fire_options(op, t)
                if not who:
                    errors.append(f"{op.route}: transition {t.from_state}->{t.to_state} can never fire "
                                  "(its rules exclude every actor)")
                edges.append((t.from_state, t.to_state, op.route, who))

        # breadth-first exploration of all operation sequences up to `depth`
        paths: dict[str, list[str]] = {m.initial: []}
        queue = deque([(m.initial, [])])
        while queue:
            state, path = queue.popleft()
            if len(path) >= depth:
                continue
            for src, dst, route, who in edges:
                if src != state or not who:
                    continue
                explored += 1
                step = f"{route} as {who[0][1]} ({who[0][0]})"
                if dst not in paths:
                    paths[dst] = path + [step]
                    queue.append((dst, path + [step]))
        terminal = set(m.terminal)
        no_actions = not any(o.entity == m.entity and o.kind != "create" and o.transitions for o in spec.operations)
        hint = (" (no route moves this entity's state; if the state is decided during the create call, put those "
                "moves on the create operation's transitions)") if no_actions else ""
        for s in m.states:
            if s not in paths:
                errors.append(f"{m.entity}: state '{s}' is unreachable from '{m.initial}' within {depth} steps{hint}")
        for src, dst, route, _who in edges:
            if src in terminal:
                errors.append(f"{m.entity}: terminal state '{src}' has a way out ({route} -> '{dst}')")
                traces.append({"entity": m.entity, "property": "terminal_closed", "trace": paths.get(src, []) + [route]})
        outgoing = {src for src, _d, _r, who in edges if who}
        for s, path in paths.items():
            if s not in terminal and s not in outgoing and terminal:
                errors.append(f"{m.entity}: non-terminal state '{s}' is a dead end (no operation leaves it)")
                traces.append({"entity": m.entity, "property": "no_dead_end", "trace": path})
        if m.initial in terminal and edges:
            errors.append(f"{m.entity}: initial state '{m.initial}' is marked terminal")
        if not terminal:
            warnings.append(f"{m.entity}: no terminal states declared")
    return SpecReport(ok=not errors, errors=errors, warnings=warnings, traces=traces, explored_paths=explored)


def check_spec(spec: BehaviorSpec, interface: dict[str, Any], depth: int = 6) -> SpecReport:
    a = validate_spec(spec, interface)
    b = model_check(spec, depth=depth)
    return SpecReport(ok=a.ok and b.ok, errors=a.errors + b.errors, warnings=a.warnings + b.warnings,
                      traces=b.traces, explored_paths=b.explored_paths)
