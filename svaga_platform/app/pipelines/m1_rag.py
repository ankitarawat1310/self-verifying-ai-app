from __future__ import annotations

import json

from shared.benchmarks.loader import BenchmarkWorkflow
from shared.budget.tracker import BudgetTracker
from shared.llm.provider import get_llm_provider

from svaga_platform.app.artifacts import PipelineArtifacts
from svaga_platform.app.pipelines.base import Pipeline, PipelineResult
from svaga_platform.app.pipelines.common import finalize_pipeline_result
from svaga_platform.app.spec_from_nl import generate_policy_from_nl, resolve_workflow_spec
from svaga_platform.app.verification.orchestrator import VerificationReport
from model1_rag_generator.backend.app.generator import generate_code_and_tests
from model1_rag_generator.backend.app.retriever import retrieve_with_provenance


class M1RagPipeline(Pipeline):
    name = "m1"

    def run(self, benchmark: BenchmarkWorkflow, *, budget: BudgetTracker, model: str | None = None) -> PipelineResult:
        prompt = benchmark.natural_language_requirement
        context, retrieval = retrieve_with_provenance(prompt, category=benchmark.category)
        llm = get_llm_provider()
        spec = resolve_workflow_spec(llm, benchmark, budget=budget)
        spec_json = json.dumps(spec.to_dict(), indent=2)
        generated = generate_code_and_tests(
            prompt,
            context,
            llm=llm,
            budget=budget,
            workflow_spec=spec.to_dict(),
        )
        policy = generate_policy_from_nl(llm, benchmark, budget=budget)
        artifacts = PipelineArtifacts(
            app_code=generated["app_code"],
            test_code=generated["test_code"],
            workflow_spec=spec,
            policy=policy,
            metadata={"retrieved_context": context, "retrieval": retrieval},
        )
        malformed_reason = generated.get("malformed_reason")
        if malformed_reason:
            return self._reject_malformed(benchmark, artifacts, budget, context, generated, malformed_reason)
        result = finalize_pipeline_result(self.name, benchmark, artifacts, budget, frozen_spec_hash=artifacts.spec_hash)
        result.metadata = {
            **result.metadata,
            "retrieved_context": context,
            "retrieval": retrieval,
        }
        return result

    def _reject_malformed(
        self,
        benchmark: BenchmarkWorkflow,
        artifacts: PipelineArtifacts,
        budget: BudgetTracker,
        context: str,
        generated: dict,
        reason: str,
    ) -> PipelineResult:
        """REJECT without running verifiers: the model produced no usable code to verify."""
        # PipelineArtifacts injects template UI/health code into app_code; keep the rejected run's files honest.
        artifacts.app_code = ""
        artifacts.test_code = ""
        counterexample = {"property_id": "generation_output", "message": reason, "spec_rule_id": "generation_output"}
        report = VerificationReport(
            passed=False,
            verifiers=[
                {
                    "name": "generation_output",
                    "passed": False,
                    "details": {"passed": False, "error": reason, "raw_preview": generated.get("malformed_raw_preview", "")},
                    "wall_seconds": 0.0,
                }
            ],
            counterexamples=[counterexample],
        )
        return PipelineResult(
            pipeline=self.name,
            workflow_id=benchmark.workflow_id,
            artifacts=artifacts,
            verification=report.to_dict(),
            decision="REJECT",
            budget=budget.to_dict(),
            counterexamples=report.counterexamples,
            metadata={"gate_reasons": [reason], "retrieved_context": context, "malformed_generation": True},
        )
