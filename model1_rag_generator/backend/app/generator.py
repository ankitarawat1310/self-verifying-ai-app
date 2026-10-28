"""RAG code generation via LLM JSON output."""

from __future__ import annotations

from typing import Any

from shared.budget.tracker import BudgetTracker
from shared.llm.provider import LLMProvider, get_llm_provider  # noqa: F401

SYSTEM = """You generate small self-contained Python applications with pytest tests.
Output JSON only: {"app_code": "...", "test_code": "..."}.
test_code must import from app (app.py in same directory).
Prefer FastAPI when the workflow describes HTTP APIs. Implement every endpoint in the spec
so the app fulfills its stated purpose (e.g. URL shortener: POST /shorten stores a URL, GET /r/{code} resolves it).
Include GET /health. Keep code minimal, correct, and fully testable.
SVAGA may inject a browser UI for common patterns; focus on solid API behavior and tests.

The app runs on FastAPI with Pydantic v2 (pydantic>=2 is installed; v1-only syntax raises at import time).
Use Pydantic v2 syntax only:
- Field(pattern=...) or constr(pattern=...), never regex=. Constrain with Field(min_length=..., max_length=..., ge=..., le=...).
- model.model_dump() and Model.model_validate(...), never .dict() or .parse_obj().
- @field_validator("name") stacked on @classmethod, and @model_validator(mode="after"), never @validator or @root_validator.
- model_config = ConfigDict(...), never an inner class Config.
- Give optional fields an explicit default, e.g. note: Optional[str] = None.

Declare every route function parameter as exactly one of:
- a path parameter: its name appears in the route path, e.g. "/items/{item_id}" with item_id: int;
- a query parameter: a simple type (str, int, float, bool) with a default, or Query(...);
- a header or cookie: Header(...) or Cookie(...);
- the request body: one Pydantic BaseModel subclass (or Body(...)).
Never leave a parameter undeclared, and never use a dict, list, or model type as a query parameter: put structured
input in a BaseModel request body. If a POST or PUT needs several fields, define one request model for them.

Request validation rules:
- Reject undeclared body fields: every request-body model (create, update and patch alike) sets
  model_config = ConfigDict(extra="forbid"), so a field the spec does not define (status, owner, role, id, ...)
  returns 422 instead of being ignored.
- Reject blank text: for every required string field, and every optional string field when it is provided, add a
  @field_validator(...) stacked on @classmethod that raises ValueError when value.strip() is empty (min_length=1
  alone accepts "   "). Validate the stripped value, not the raw one, and
  always end the validator with `return value`: a validator that returns nothing sets the field to None.
- Use the exact field and key names from the task interface for every request field, response field and outbound
  payload sent to another service (e.g. event_id, not id). Never rename, abbreviate or add prefixes to a key the
  interface spells out.

Identity headers (when the interface lists actor/role headers): the actor id is any plain string, never a UUID or
int. Declare each header with its exact interface name, e.g. for x-actor-id and x-actor-role:
    x_actor_id: Optional[str] = Header(None, alias="x-actor-id"),
    x_actor_role: Optional[str] = Header(None, alias="x-actor-role"),
(a parameter named actor_id would read a header called "actor-id" and never see x-actor-id). Answer a missing,
partial or unknown identity with the interface's forbidden code (403) yourself, so FastAPI never turns a missing
header into 422.
List routes return a bare JSON array of items, not an object wrapping the list.

Test independence: the app keeps its data in memory and every test in test_code shares that one app, so tests must
not depend on each other or on their order. Either reset the app's state before each test (an autouse pytest
fixture that clears the app's module-level stores, e.g. `app_module.items_db.clear()`), or give every test its
own unique data (fresh emails, usernames, ids, and non-overlapping dates or time slots, e.g. built from uuid4()).
Never reuse a unique-constrained value across tests, never assert on the total size of a shared list without
resetting state first, and never assume an earlier test has already created a record. Pydantic may normalize values
(e.g. lower-case an email); compare such values case-insensitively in tests."""


MALFORMED_PREFIX = "malformed generation output"

_CODE_KEYS = ("app_code", "test_code")
# Top-level WorkflowSpec fields; small models sometimes echo the prompt's spec back instead of code.
_SPEC_KEYS = frozenset(
    {"workflow_id", "application_name", "actors", "entities", "business_rules", "endpoints", "invariants"}
)
_PREVIEW_CHARS = 500


def _malformed(detail: str, raw: Any) -> dict[str, Any]:
    return {
        "app_code": "",
        "test_code": "",
        "malformed_reason": f"{MALFORMED_PREFIX}: {detail}",
        "malformed_raw_preview": repr(raw)[:_PREVIEW_CHARS],
    }


def validate_generation(raw: Any) -> dict[str, Any]:
    """Normalize an LLM response into a dict that always has string ``app_code``/``test_code``.

    Never raises. On a malformed response the code fields are empty and ``malformed_reason``
    (prefixed with ``MALFORMED_PREFIX``) explains why; callers should treat that as a REJECT.
    """
    if not isinstance(raw, dict):
        return _malformed(f"expected a JSON object, got {type(raw).__name__}", raw)

    missing = [k for k in _CODE_KEYS if k not in raw]
    if missing:
        echoed = sorted(_SPEC_KEYS & raw.keys())
        if len(echoed) >= 3:
            return _malformed(
                "model echoed the WorkflowSpec instead of code "
                f"(spec keys: {', '.join(echoed)}; missing: {', '.join(missing)})",
                raw,
            )
        return _malformed(f"missing required key(s): {', '.join(missing)}", raw)

    for key in _CODE_KEYS:
        value = raw[key]
        if not isinstance(value, str):
            return _malformed(f"'{key}' must be a string, got {type(value).__name__}", raw)
        if not value.strip():
            return _malformed(f"'{key}' is empty", raw)

    return raw


def generate_code_and_tests(
    user_prompt: str,
    context: str,
    *,
    llm: LLMProvider | None = None,
    budget: BudgetTracker | None = None,
    workflow_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ask the LLM for app + tests and return a validated dict.

    Malformed model output (non-JSON, wrong shape, missing/empty/non-string code keys, echoed
    WorkflowSpec) does not raise: the result carries ``malformed_reason`` with empty code.
    Provider/transport errors and ``BudgetExceeded`` still propagate.
    """
    import json

    llm = llm or get_llm_provider()
    spec_block = ""
    if workflow_spec:
        spec_block = (
            f"\n\nImplement workflow_id={workflow_spec.get('workflow_id')} exactly.\n"
            f"Frozen WorkflowSpec:\n{json.dumps(workflow_spec, indent=2)}\n"
        )
    user = f"User request:\n{user_prompt}{spec_block}\n\nReference context:\n{context}"
    try:
        raw = llm.complete_json(SYSTEM, user, budget=budget)
    except ValueError as exc:  # json.JSONDecodeError (invalid JSON from the model) is a ValueError
        return _malformed(f"response was not valid JSON ({exc})", None)
    return validate_generation(raw)
