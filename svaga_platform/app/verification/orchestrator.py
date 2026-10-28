from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from shared.benchmarks.loader import BenchmarkWorkflow
from shared.budget.tracker import BudgetTracker
from shared.policy.checker import check_policy_static
from shared.sandbox.pytest_runner import execute_pytest_sandbox
from shared.schemas.workflow_spec import WorkflowSpecDocument

from svaga_platform.app.artifacts import PipelineArtifacts
from svaga_platform.app.verification.contract_checks import check_contract
from svaga_platform.app.verification.fuzz_runner import run_api_fuzz
from svaga_platform.app.verification.hypothesis_runner import run_hypothesis_suite
from svaga_platform.app.verification.invariants import check_spec_invariants
from svaga_platform.app.verification.property_runner import run_benchmark_properties


@dataclass
class VerificationReport:
    passed: bool
    verifiers: list[dict[str, Any]] = field(default_factory=list)
    counterexamples: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "verifiers": self.verifiers,
            "counterexamples": self.counterexamples,
        }


def run_full_verification(
    artifacts: PipelineArtifacts,
    benchmark: BenchmarkWorkflow | None,
    budget: BudgetTracker,
    *,
    profile: str = "pragmatic",
) -> VerificationReport:
    budget.begin_verification()
    verifiers: list[dict[str, Any]] = []
    counterexamples: list[dict[str, Any]] = []

    def _run(name: str, fn) -> bool:
        start = time.monotonic()
        try:
            result = fn()
            passed = bool(result.get("passed") if isinstance(result, dict) else result.passed)
            detail = result if isinstance(result, dict) else result.to_dict()
        except Exception as exc:  # pragma: no cover - surfaced in report
            passed = False
            detail = {"error": str(exc)}
        verifiers.append({"name": name, "passed": passed, "details": detail, "wall_seconds": round(time.monotonic() - start, 3)})
        if not passed:
            counterexamples.append({"property_id": name, "message": str(detail), "spec_rule_id": name})
        return passed

    extra = {"test_properties.py": artifacts.test_properties_code} if artifacts.test_properties_code else None
    test_bundle = artifacts.test_code

    def _pytest_check() -> dict[str, Any]:
        sandbox = execute_pytest_sandbox(artifacts.app_code, test_bundle, extra_files=extra)
        payload = sandbox.to_dict()
        payload["passed"] = sandbox.passed
        return payload

    ok_pytest = _run("pytest_sandbox", _pytest_check)

    if artifacts.test_properties_code:
        _run(
            "hypothesis",
            lambda: run_hypothesis_suite(artifacts.app_code, artifacts.test_properties_code).to_dict(),
        )

    if isinstance(artifacts.workflow_spec, WorkflowSpecDocument):
        _run(
            "contract_checks",
            lambda: check_contract(artifacts.workflow_spec, artifacts.app_code).to_dict(),
        )
        _run(
            "spec_invariants",
            lambda: check_spec_invariants(artifacts.workflow_spec, artifacts.app_code).to_dict(),
        )

    _run("policy_static", lambda: check_policy_static(artifacts.app_code, artifacts.policy).to_dict())

    if profile != "minimal":
        _run("api_fuzz", lambda: run_api_fuzz(artifacts.app_code, artifacts.spec_dict()).to_dict())

    if benchmark:
        _run(
            "benchmark_properties",
            lambda: run_benchmark_properties(artifacts.app_code, artifacts.test_code, benchmark).to_dict(),
        )

    budget.end_verification()
    passed = ok_pytest and all(v["passed"] for v in verifiers)
    return VerificationReport(passed=passed, verifiers=verifiers, counterexamples=counterexamples if not passed else [])
