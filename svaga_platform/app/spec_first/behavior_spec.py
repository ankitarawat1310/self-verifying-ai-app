"""BehaviorSpec: the machine-checkable spec M2 writes before any code.

The public interface already fixes routes, roles, request fields and status codes. The LLM adds what the interface
does not say: which route creates which entity, the status state machine, per-transition roles, and rules such as
"requester cannot approve own request" or "end_date >= start_date". The spec is frozen (hashed) before code exists.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

OpKind = Literal["create", "read", "list", "update", "delete", "action", "other"]
RuleKind = Literal["not_self", "owner_only", "field_order", "unique", "custom"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Transition(_Strict):
    from_state: str
    to_state: str
    roles: list[str] = Field(default_factory=list)  # empty = the operation's roles


class Rule(_Strict):
    kind: RuleKind
    description: str = ""
    fields: list[str] = Field(default_factory=list)  # field_order: [left, right]; unique: [field]; not_self/owner_only: [owner_field]
    op: Optional[Literal["<", "<=", ">", ">="]] = None  # field_order: left op right must hold
    error_status: int = 422


class Operation(_Strict):
    route: str  # "METHOD /path"
    kind: OpKind = "other"
    entity: str = ""
    roles: list[str] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)


class StateMachine(_Strict):
    entity: str
    field: str = "status"
    initial: str
    states: list[str]
    terminal: list[str] = Field(default_factory=list)


class SpecPolicy(_Strict):
    allowed_imports: list[str] = Field(default_factory=lambda: ["fastapi", "pydantic", "typing", "uuid", "datetime"])
    forbidden_imports: list[str] = Field(default_factory=lambda: ["subprocess", "socket", "os.system", "ctypes"])
    outbound_hosts: list[str] = Field(default_factory=list)


class BehaviorSpec(_Strict):
    task_id: str
    entities: list[str] = Field(default_factory=list)
    operations: list[Operation]
    state_machines: list[StateMachine] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)
    policy: SpecPolicy = Field(default_factory=SpecPolicy)

    def op(self, route: str) -> Operation | None:
        return next((o for o in self.operations if o.route == route), None)

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def spec_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


def route_key(route: dict[str, Any]) -> str:
    return f"{route['method'].upper()} {route['path']}"


def _guess_kind(route: dict[str, Any]) -> OpKind:
    method, path = route["method"].upper(), route["path"]
    has_id = path.rstrip("/").endswith("}")
    if method == "POST" and "{" not in path:
        return "create"
    if method == "GET":
        return "read" if has_id else "list"
    if method in ("PATCH", "PUT") and has_id:
        return "update"
    if method == "DELETE":
        return "delete"
    if method == "POST" and "{" in path:
        return "action"
    return "other"


def _entity_of(path: str) -> str:
    first = path.strip("/").split("/")[0] if path.strip("/") else "root"
    return first.replace("-", "_")


def skeleton_from_interface(task_id: str, interface: dict[str, Any]) -> BehaviorSpec:
    """Interface-only spec: routes, roles and a guessed kind. No state machine, no rules. Also the fallback spec."""
    ops = [
        Operation(route=route_key(r), kind=_guess_kind(r), entity=_entity_of(r["path"]), roles=list(r.get("roles", [])))
        for r in interface.get("routes", [])
    ]
    from urllib.parse import urlsplit

    hosts = sorted({urlsplit(str(m["url"])).netloc for m in interface.get("mock_services") or [] if m.get("url")})
    return BehaviorSpec(
        task_id=task_id,
        entities=sorted({o.entity for o in ops}),
        operations=ops,
        policy=SpecPolicy(outbound_hosts=hosts),
    )


def llm_json_schema() -> dict[str, Any]:
    """JSON schema passed to Ollama's structured output so the reply has the BehaviorSpec shape."""
    return BehaviorSpec.model_json_schema()
