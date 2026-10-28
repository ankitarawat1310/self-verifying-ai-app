"""M0: plain-prompt baseline (what an unverified code agent does today).

One LLM call with the same generator instructions as M1 but no retrieved context and no spec. The model writes the
app and its own tests; M0 ships (ACCEPT) when its own tests pass in the sandbox. No policy, contract, fuzzing or
property checks. The hidden judge later shows how often that self-assessment is wrong (false assurance).
"""
from __future__ import annotations

import time

from shared.benchmarks.loader import BenchmarkWorkflow
from shared.budget.tracker import BudgetTracker
from shared.llm.provider import get_llm_provider
from shared.sandbox.pytest_runner import execute_pytest_sandbox

from svaga_platform.app.artifacts import PipelineArtifacts
from svaga_platform.app.pipelines.base import Pipeline, PipelineResult
from svaga_platform.app.pipelines.common import default_policy_from_benchmark, minimal_spec_from_benchmark
from svaga_platform.app.verification.orchestrator import VerificationReport
from model1_rag_generator.backend.app.generator import generate_code_and_tests

NO_CONTEXT = "# --- RETRIEVED CONTEXT ---\n(none: M0 uses no retrieval)\n# --- END RETRIEVED CONTEXT ---"


class M0PlainPipeline(Pipeline):
    name = "m0"

    def run(self, benchmark: BenchmarkWorkflow, *, budget: BudgetTracker, model: str | None = None) -> PipelineResult:
        llm = get_llm_provider()
        generated = generate_code_and_tests(benchmark.natural_language_requirement, NO_CONTEXT, llm=llm, budget=budget)
        artifacts = PipelineArtifacts(
            app_code=generated["app_code"],
            test_code=generated["test_code"],
            workflow_spec=minimal_spec_from_benchmark(benchmark),
            policy=default_policy_from_benchmark(benchmark),
        )
        if generated.get("malformed_reason"):
            artifacts.app_code, artifacts.test_code = "", ""
            reason = generated["malformed_reason"]
            report = VerificationReport(
                passed=False,
                verifiers=[{"name": "generation_output", "passed": False, "details": {"error": reason}, "wall_seconds": 0.0}],
                counterexamples=[{"property_id": "generation_output", "message": reason, "spec_rule_id": "generation_output"}],
            )
            return PipelineResult(self.name, benchmark.workflow_id, artifacts, report.to_dict(), "REJECT",
                                  budget.to_dict(), report.counterexamples, {"gate_reasons": [reason],
                                                                              "self_check": "own tests only"})
        budget.begin_verification()
        started = time.monotonic()
        sandbox = execute_pytest_sandbox(artifacts.app_code, artifacts.test_code)
        budget.end_verification()
        passed = bool(sandbox.passed)
        details = {**sandbox.to_dict(), "passed": passed}
        report = VerificationReport(
            passed=passed,
            verifiers=[{"name": "own_tests", "passed": passed, "details": details,
                        "wall_seconds": round(time.monotonic() - started, 3)}],
            counterexamples=[] if passed else [{"property_id": "own_tests", "message": "generated tests failed",
                                                "spec_rule_id": "own_tests"}],
        )
        return PipelineResult(
            pipeline=self.name,
            workflow_id=benchmark.workflow_id,
            artifacts=artifacts,
            verification=report.to_dict(),
            decision="ACCEPT" if passed else "REJECT",
            budget=budget.to_dict(),
            counterexamples=report.counterexamples,
            metadata={"gate_reasons": [] if passed else ["own tests failed"], "self_check": "own tests only"},
        )
