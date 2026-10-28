from __future__ import annotations

from shared.benchmarks.loader import BenchmarkWorkflow
from shared.budget.tracker import BudgetTracker
from shared.llm.provider import get_llm_provider

from svaga_platform.app.artifacts import PipelineArtifacts
from svaga_platform.app.pipelines.base import Pipeline, PipelineResult
from svaga_platform.app.pipelines.m2_spec_first import M2SpecFirstPipeline


class M3InvariantsPipeline(Pipeline):
    name = "m3"

    def run(self, benchmark: BenchmarkWorkflow, *, budget: BudgetTracker, model: str | None = None) -> PipelineResult:
        baseline = M2SpecFirstPipeline().run(benchmark, budget=budget, model=model)
        llm = get_llm_provider()
        prop = llm.complete_json(
            "Generate Hypothesis test_properties.py for the spec.",
            f"Spec:\n{baseline.artifacts.spec_dict()}",
            budget=budget,
        )
        baseline.artifacts.test_properties_code = prop.get("test_properties_code", "")
        from svaga_platform.app.pipelines.common import finalize_pipeline_result

        return finalize_pipeline_result(
            self.name,
            benchmark,
            baseline.artifacts,
            budget,
            frozen_spec_hash=baseline.artifacts.spec_hash,
            profile="pragmatic",
        )
