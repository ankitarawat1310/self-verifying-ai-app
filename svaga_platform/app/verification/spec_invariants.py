"""Evaluate spec and benchmark safety rules as executable predicates."""

from __future__ import annotations

from typing import Any


def evaluate_spec_invariants(
    workflow_spec: dict[str, Any],
    benchmark: dict[str, Any] | None = None,
) -> dict[str, Any]:
    violations: list[str] = []
    if not workflow_spec.get("workflow_id"):
        violations.append("missing workflow_id")
    if not workflow_spec.get("initial_state"):
        violations.append("missing initial_state")
    init = workflow_spec.get("initial_state")
    states = set(workflow_spec.get("states", []))
    if init and states and init not in states:
        violations.append("initial_state not in states")

    for rule in workflow_spec.get("business_rules", []):
        if not rule.get("name") or not rule.get("description"):
            violations.append("business_rule incomplete")

    if benchmark:
        for sp in benchmark.get("safety_properties", []):
            predicate = sp.get("predicate")
            if predicate == "no_self_approval":
                # static spec check: approver role distinct from submitter
                actors = {a.get("id") for a in workflow_spec.get("actors", [])}
                if "approver" in actors and "employee" in actors:
                    pass
                elif sp.get("required", False):
                    violations.append("safety:no_self_approval actors missing")

    return {"passed": len(violations) == 0, "violations": violations}
