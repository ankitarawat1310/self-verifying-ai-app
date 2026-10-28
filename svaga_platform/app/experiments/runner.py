from __future__ import annotations

import csv
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.benchmarks.loader import BenchmarkWorkflow
from shared.benchmarks.task_package import find_benchmark
from shared.budget.tracker import BudgetProfile, BudgetTracker
from shared.paths import BENCHMARKS_DIR, RESULTS_DIR

from svaga_platform.app.pipelines.registry import get_pipeline


@dataclass
class ExperimentMetrics:
    functional_pass_rate: float = 0.0
    repair_success: float = 0.0
    verification_time_seconds: float = 0.0
    permission_excess: float = 0.0
    llm_tokens: int = 0
    rows: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "functional_pass_rate": self.functional_pass_rate,
            "repair_success": self.repair_success,
            "verification_time_seconds": self.verification_time_seconds,
            "permission_excess": self.permission_excess,
            "llm_tokens": self.llm_tokens,
            "rows": self.rows,
        }


def run_experiment(
    workflow_ids: list[str],
    pipelines: list[str],
    *,
    budget_profile: BudgetProfile | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    budget_profile = budget_profile or BudgetProfile()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out = output_dir or (RESULTS_DIR / run_id)
    out.mkdir(parents=True, exist_ok=True)

    metrics = ExperimentMetrics()
    results: list[dict[str, Any]] = []

    for wf_id in workflow_ids:
        benchmark = find_benchmark(wf_id)
        for pipe_name in pipelines:
            pipeline = get_pipeline(pipe_name)
            budget = BudgetTracker(profile=budget_profile)
            result = pipeline.run(benchmark, budget=budget)
            payload = result.to_dict()
            payload["run_id"] = run_id
            results.append(payload)
            (out / f"{wf_id}_{pipeline.name}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

            functional_ok = result.decision == "ACCEPT"
            metrics.rows.append(
                {
                    "workflow_id": wf_id,
                    "pipeline": pipeline.name,
                    "decision": result.decision,
                    "functional_pass": functional_ok,
                    "verification_seconds": budget.verification_seconds,
                    "tokens": budget.tokens_used,
                    "repair_rounds": budget.repair_rounds,
                }
            )
            metrics.verification_time_seconds += budget.verification_seconds
            metrics.llm_tokens += budget.tokens_used

    if metrics.rows:
        metrics.functional_pass_rate = sum(1 for r in metrics.rows if r["functional_pass"]) / len(metrics.rows)
        m4_rows = [r for r in metrics.rows if r["pipeline"] == "m4"]
        if m4_rows:
            metrics.repair_success = sum(1 for r in m4_rows if r["decision"] == "ACCEPT") / len(m4_rows)

    summary = {"run_id": run_id, "metrics": metrics.to_dict(), "result_count": len(results)}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _export_csv(out / "metrics.csv", metrics.rows)
    return summary


def _export_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
