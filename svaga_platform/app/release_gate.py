from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from svaga_platform.app.verification.orchestrator import VerificationReport


@dataclass
class GateDecision:
    decision: str
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"decision": self.decision, "reasons": self.reasons}


def evaluate_release_gate(
    verification: VerificationReport,
    *,
    spec_hash: str,
    frozen_spec_hash: str | None,
    policy_passed: bool,
) -> GateDecision:
    reasons: list[str] = []
    if not verification.passed:
        reasons.append("verification failed")
    if verification.counterexamples:
        reasons.append("open counterexamples")
    if frozen_spec_hash and spec_hash != frozen_spec_hash:
        reasons.append("spec hash changed after freeze")
    if not policy_passed:
        reasons.append("policy check failed")

    decision = "ACCEPT" if not reasons else "REJECT"
    return GateDecision(decision=decision, reasons=reasons)
