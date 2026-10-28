from __future__ import annotations

from typing import Any

from shared.benchmarks.adhoc import adhoc_benchmark_from_nl
from shared.benchmarks.loader import BenchmarkWorkflow
from shared.benchmarks.task_package import find_benchmark
from shared.budget.tracker import BudgetProfile, BudgetTracker

from svaga_platform.app.pipelines.base import PipelineResult
from svaga_platform.app.pipelines.registry import get_pipeline
from svaga_platform.app.run_store import new_run_id, persist_run
from svaga_platform.app.spec_from_nl import llm_provider_label


def resolve_benchmark(
    natural_language: str,
    workflow_id: str | None,
) -> BenchmarkWorkflow:
    if workflow_id:
        bench = find_benchmark(workflow_id)
        if bench.raw.get("benchmark_version") == "v1":
            # v1 public task: the interface contract is always appended to whatever prompt the user typed
            return find_benchmark(workflow_id, natural_language)
        if natural_language.strip():
            bench = BenchmarkWorkflow(
                workflow_id=bench.workflow_id,
                name=bench.name,
                category=bench.category,
                natural_language_requirement=natural_language.strip(),
                raw={**bench.raw, "natural_language_requirement": natural_language.strip()},
            )
        return bench
    return adhoc_benchmark_from_nl(natural_language.strip())


def run_workflow(
    *,
    pipeline: str,
    natural_language: str,
    workflow_id: str | None = None,
    budget: BudgetTracker | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    budget = budget or BudgetTracker(profile=BudgetProfile())
    benchmark = resolve_benchmark(natural_language, workflow_id)
    pipe = get_pipeline(pipeline)
    result: PipelineResult = pipe.run(benchmark, budget=budget)

    provenance = {
        **result.metadata,
        "llm": llm_provider_label(),
        "benchmark_workflow_id": benchmark.workflow_id,
        "natural_language": benchmark.natural_language_requirement,
    }
    run_id = new_run_id()
    payload = result.to_dict()
    payload["run_id"] = run_id
    payload["release_gate"] = {
        "decision": result.decision,
        "reasons": result.metadata.get("gate_reasons", []),
    }
    payload["provenance"] = provenance

    if persist:
        persist_run(run_id, payload)

    return payload
