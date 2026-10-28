"""LLM steps of M2: author the BehaviorSpec (with one fix round), then synthesize app code from the frozen spec."""
from __future__ import annotations

import inspect
import json
from typing import Any

from pydantic import ValidationError

from shared.budget.tracker import BudgetTracker
from shared.llm.provider import LLMProvider
from svaga_platform.app.spec_first.behavior_spec import BehaviorSpec, SpecPolicy, llm_json_schema, skeleton_from_interface
from svaga_platform.app.spec_first.spec_check import SpecReport, check_spec, rule_problem

SKELETON_BEGIN = "SKELETON_JSON_BEGIN"
SKELETON_END = "SKELETON_JSON_END"
ALWAYS_FORBIDDEN = ["subprocess", "socket", "ctypes", "os.system"]

SPEC_SYSTEM = """You are the BehaviorSpec author for a small FastAPI service. You write the behavior spec BEFORE any
code exists; code and tests will later be generated from your spec, so be precise and only state what the
requirement says or clearly implies.

Output JSON only, one BehaviorSpec object. Start from the skeleton you are given (it already lists every route with
its roles) and fill in:
- operations[].kind: create | read | list | update | delete | action | other.
- operations[].entity: the entity the route works on (the same name for all routes of one resource).
- state_machines: one per entity that has a status/lifecycle field. field is the response field holding the state
  (usually "status"), initial is the state right after create, states lists every value, terminal lists states
  that can never change again.
- operations[].transitions: for each action route, every from_state -> to_state move it performs. If only some of
  the route's roles may make a particular move, list them in that transition's roles.
- operations[].rules, each with error_status (the HTTP code the interface gives for that failure):
  - not_self: the actor must NOT be the entity's owner (fields: [owner field, e.g. "requester_id"]).
  - owner_only: the actor MUST be the entity's owner (fields: [owner field]).
  - field_order: fields [left, right] with op "<", "<=", ">" or ">=" that must hold (e.g. start_date <= end_date).
  - unique: fields [field] whose value may not repeat.
  - custom: anything else, described in words.
  Do not restate single-field limits (required, not blank, > 0, max length): the interface already has them.
  field_order is only for two date, datetime or number fields of the same type. not_self and owner_only need
  identity headers; the owner field is the field holding the creator's actor id (e.g. "requester_id"), never "id".
- If a record's state is decided during the create call itself (for example by an outside service's answer),
  put those moves on the create operation's transitions, from the initial state; several outcomes are allowed there.
  Every action route that changes a record's status (approve, reject, start, close, ...) needs transitions.
- invariants: short sentences that must always hold.
- policy: imports the code may use, imports it must not use, and outbound hosts it may call (only hosts named in
  the interface).
Keep every route exactly as spelled in the skeleton. Do not add routes, roles, fields or states the requirement
does not mention."""

SYNTH_SYSTEM_HEAD = """You implement a FastAPI app from a FROZEN BehaviorSpec. The spec is final: implement it exactly,
do not change it. Output JSON only: {"app_code": "..."}. Tests are generated separately from the spec, so write
only the app.
Implement every route of the interface, enforce every role, transition, rule and terminal state in the spec, and
answer with the interface's status codes. A move that the state machine does not allow from the current state is a
conflict. Check identity/role first, then the entity exists, then owner rules, then the state."""


def _call(llm: LLMProvider, system: str, user: str, budget: BudgetTracker | None, schema: dict[str, Any] | None) -> Any:
    params = inspect.signature(llm.complete_json).parameters
    if schema is not None and ("schema" in params or any(p.kind == p.VAR_KEYWORD for p in params.values())):
        return llm.complete_json(system, user, budget=budget, schema=schema)
    return llm.complete_json(system, user, budget=budget)


RULE_STATUS = {"not_self": "forbidden", "owner_only": "forbidden", "unique": "conflict", "field_order": "validation_error"}


def normalize(raw: Any, skeleton: BehaviorSpec, interface: dict[str, Any] | None = None) -> tuple[BehaviorSpec | None, list[str]]:
    """Parse the LLM reply and pin it to the interface: routes and roles come from the interface, not the LLM.

    With the interface given, each rule's error status is set from the interface's status codes (the interface
    says what 403/409/422 mean), and rules that cannot apply to the route (e.g. field_order on two strings, an
    owner rule on an API without identity headers) are dropped with a note.

    Returns (spec or None, notes). Notes say what was changed so the run record shows it.
    """
    notes: list[str] = []
    if isinstance(raw, dict) and "spec" in raw and isinstance(raw["spec"], dict):
        raw = raw["spec"]
    if not isinstance(raw, dict):
        return None, [f"spec reply was {type(raw).__name__}, not an object"]
    raw = dict(raw)
    raw["task_id"] = skeleton.task_id
    try:
        spec = BehaviorSpec.model_validate(raw)
    except ValidationError as exc:
        return None, [f"spec does not match the BehaviorSpec shape: {e['loc']}: {e['msg']}" for e in exc.errors()[:8]]
    by_route = {o.route: o for o in skeleton.operations}
    kept, seen = [], set()
    for op in spec.operations:
        if op.route not in by_route:
            notes.append(f"dropped operation {op.route}: not an interface route")
            continue
        if op.route in seen:
            notes.append(f"dropped duplicate operation {op.route}")
            continue
        seen.add(op.route)
        if sorted(op.roles) != sorted(by_route[op.route].roles):
            notes.append(f"{op.route}: roles reset to the interface's {by_route[op.route].roles}")
            op.roles = list(by_route[op.route].roles)
        if not op.entity:
            op.entity = by_route[op.route].entity
        kept.append(op)
    for route, op in by_route.items():
        if route not in seen:
            notes.append(f"added missing operation {route} from the interface")
            kept.append(op.model_copy())
    spec.operations = kept
    if interface is not None:
        codes = interface.get("status_codes") or {}
        for op in spec.operations:
            keep = []
            for rule in op.rules:
                meaning = RULE_STATUS.get(rule.kind)
                if meaning and meaning in codes and rule.error_status != codes[meaning]:
                    notes.append(f"{op.route}: {rule.kind} error_status {rule.error_status} set to the interface's "
                                 f"{meaning} code {codes[meaning]}")
                    rule.error_status = int(codes[meaning])
                problem = rule_problem(rule, op, interface, spec)
                if problem:
                    notes.append(f"{op.route}: dropped {rule.kind} rule: {problem}")
                    continue
                keep.append(rule)
            op.rules = keep
    spec.entities = sorted({o.entity for o in kept})
    spec.policy = SpecPolicy(
        allowed_imports=spec.policy.allowed_imports,
        forbidden_imports=sorted(set(spec.policy.forbidden_imports) | set(ALWAYS_FORBIDDEN)),
        outbound_hosts=[h for h in spec.policy.outbound_hosts if h in skeleton.policy.outbound_hosts],
    )
    return spec, notes


def author_spec(
    llm: LLMProvider,
    task_id: str,
    requirement: str,
    interface: dict[str, Any],
    *,
    budget: BudgetTracker | None = None,
    max_fix_rounds: int = 1,
) -> tuple[BehaviorSpec, dict[str, Any]]:
    """Ask for a spec, check it, give the errors back once, and fall back to the interface skeleton if still bad."""
    skeleton = skeleton_from_interface(task_id, interface)
    base_user = (
        f"Requirement:\n{requirement}\n\nSkeleton (fill it in and return the whole spec):\n"
        f"{SKELETON_BEGIN}\n{skeleton.model_dump_json(indent=2)}\n{SKELETON_END}"
    )
    history: list[dict[str, Any]] = []
    user = base_user
    for attempt in range(max_fix_rounds + 1):
        raw = _call(llm, SPEC_SYSTEM, user, budget, llm_json_schema())
        spec, notes = normalize(raw, skeleton, interface)
        report = check_spec(spec, interface) if spec else SpecReport(ok=False, errors=notes)
        history.append({"attempt": attempt, "notes": notes, "report": report.to_dict()})
        if spec is not None and report.ok:
            return spec, {"source": "llm", "attempts": attempt + 1, "history": history}
        problems = report.errors or notes
        user = (
            base_user
            + "\n\nYour previous spec failed these checks. Fix every one and return the whole corrected spec:\n- "
            + "\n- ".join(problems[:20])
            + (f"\nPrevious spec:\n{spec.model_dump_json()}" if spec else "")
        )
    return skeleton, {"source": "skeleton_fallback", "attempts": max_fix_rounds + 1, "history": history}


def synth_system() -> str:
    """Generator rules shared with M0/M1 (Pydantic v2, extra=forbid, blank rejection, exact names), minus test rules."""
    from model1_rag_generator.backend.app.generator import SYSTEM

    shared = SYSTEM.split("The app runs on FastAPI", 1)[1].split("Test independence", 1)[0]
    return SYNTH_SYSTEM_HEAD + "\n\nThe app runs on FastAPI" + shared.rstrip()


def synthesize_app(
    llm: LLMProvider,
    requirement: str,
    spec: BehaviorSpec,
    context: str,
    *,
    budget: BudgetTracker | None = None,
) -> dict[str, Any]:
    user = (
        f"User request:\n{requirement}\n\nFrozen BehaviorSpec (spec_hash {spec.spec_hash()}):\n"
        f"{spec.model_dump_json(indent=2)}\n\nReference context:\n{context}"
    )
    schema = {"type": "object", "properties": {"app_code": {"type": "string"}}, "required": ["app_code"]}
    try:
        raw = _call(llm, synth_system(), user, budget, schema)
    except ValueError as exc:
        return {"app_code": "", "malformed_reason": f"malformed generation output: response was not valid JSON ({exc})"}
    if not isinstance(raw, dict) or not isinstance(raw.get("app_code"), str) or not raw["app_code"].strip():
        return {"app_code": "", "malformed_reason": "malformed generation output: missing or empty app_code",
                "malformed_raw_preview": repr(raw)[:500]}
    return {"app_code": raw["app_code"]}
