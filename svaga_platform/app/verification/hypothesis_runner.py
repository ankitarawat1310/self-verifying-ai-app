from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared.sandbox.pytest_runner import execute_pytest_sandbox


@dataclass
class HypothesisRunResult:
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, **self.details}


def run_hypothesis_suite(app_code: str, test_properties_code: str) -> HypothesisRunResult:
    if not test_properties_code.strip():
        return HypothesisRunResult(passed=True, details={"skipped": True})
    sandbox = execute_pytest_sandbox(app_code, test_properties_code, timeout=45)
    return HypothesisRunResult(passed=sandbox.passed, details={"sandbox": sandbox.to_dict()})
