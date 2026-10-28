from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared.schemas.workflow_spec import WorkflowSpecDocument


@dataclass
class InvariantCheckResult:
    passed: bool
    violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "violations": self.violations}


def check_spec_invariants(spec: WorkflowSpecDocument, app_code: str) -> InvariantCheckResult:
    violations: list[str] = []
    for inv in spec.invariants:
        if inv.lower().startswith("no self") and "self" in app_code.lower() and "approve" in app_code.lower():
            if "requester" in app_code.lower() and "approver" in app_code.lower():
                pass  # heuristic placeholder
    for rule in spec.business_rules:
        if rule.id == "no_self_approval" and "approver_id == requester_id" not in app_code.replace(" ", ""):
            if "self" in rule.description.lower():
                violations.append("missing no_self_approval guard")
    return InvariantCheckResult(passed=len(violations) == 0, violations=violations)
