from __future__ import annotations

import json

from shared.benchmarks.loader import BenchmarkWorkflow
from shared.budget.tracker import BudgetTracker
from shared.llm.provider import get_llm_provider

from svaga_platform.app.pipelines.base import Pipeline, PipelineResult
from svaga_platform.app.pipelines.m3_invariants import M3InvariantsPipeline
from svaga_platform.app.pipelines.repair import apply_repair_patch, build_counterexample


class M4CegrPipeline(Pipeline):
    name = "m4"

    def run(self, benchmark: BenchmarkWorkflow, *, budget: BudgetTracker, model: str | None = None) -> PipelineResult:
        result = M3InvariantsPipeline().run(benchmark, budget=budget, model=model)
        if result.decision == "ACCEPT":
            result.metadata["repair_rounds"] = 0
            return result

        llm = get_llm_provider()
        frozen_spec = result.artifacts.spec_hash
        frozen_policy = result.artifacts.policy.model_dump_json()
        rounds = 0
        while result.decision == "REJECT" and rounds < budget.profile.max_repair_rounds:
            rounds += 1
            budget.record_repair_round()
            cx = build_counterexample(result)
            repair_prompt = (
                "Repair agent: fix app_code only. Forbidden: editing spec or policy.\n"
                f"Counterexample:\n{json.dumps(cx, indent=2)}\n"
                f"Spec hash (frozen): {frozen_spec}\n"
                f"Current app:\n{result.artifacts.app_code}"
            )
            proposal = llm.complete_json("repair counterexample-guided", repair_prompt, budget=budget)
            patched_app = apply_repair_patch(result.artifacts.app_code, proposal.get("patch") or proposal.get("app_code", ""))
            result.artifacts.app_code = patched_app
            from svaga_platform.app.pipelines.common import finalize_pipeline_result

            result = finalize_pipeline_result(
                self.name,
                benchmark,
                result.artifacts,
                budget,
                frozen_spec_hash=frozen_spec,
            )
            if result.artifacts.policy.model_dump_json() != frozen_policy:
                result.decision = "REJECT"
                result.counterexamples.append(
                    {"property_id": "policy_freeze", "message": "policy mutation detected during repair"}
                )
                break

        result.metadata["repair_rounds"] = rounds
        return result
