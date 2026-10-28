"""Summarize a results/grid/<name> folder: one row per model, saved as summary.json, summary.csv and summary.md.

    python scripts/summarize_grid.py results/grid/smoke
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from svaga_platform.app.experiments.grid import load_records  # noqa: E402
from svaga_platform.app.experiments.metrics import summarize  # noqa: E402

COLUMNS = [
    ("runs", "Runs"), ("errors", "Errors"), ("accepted", "Accepted"),
    ("functional_pass_rate", "Functional pass"), ("hidden_check_rate", "Hidden checks passed"),
    ("safety_check_rate", "Safety checks passed"), ("false_assurance_rate", "False assurance (of accepted)"),
    ("broken_shipped_rate", "Broken apps shipped"), ("false_rejection_rate", "False rejection (of rejected)"),
    ("violation_recall", "Benchmark bugs caught by own tests"),
    ("own_mutation_score", "Own-app mutants caught by own tests"), ("permission_excess_mean", "Excess imports"),
    ("tokens_mean", "Tokens"), ("llm_calls_mean", "LLM calls"),
    ("verification_seconds_mean", "Verification s"), ("wall_seconds_mean", "Wall s"),
]


def _fmt(v) -> str:
    if v is None:
        return "-"
    return f"{v:.2f}" if isinstance(v, float) else str(v)


def print_and_save(out: Path) -> dict:
    records = load_records(out)
    summary = summarize(records)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with open(out / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["model"] + [label for _, label in COLUMNS])
        for model, row in summary.items():
            w.writerow([model] + [row[k] for k, _ in COLUMNS])
    with open(out / "runs.csv", "w", newline="", encoding="utf-8") as f:
        keys = ["model", "task", "category", "repeat", "decision", "hidden_passed", "hidden_total", "hidden_pass",
                "false_assurance", "false_rejection", "violation_recall", "own_mutation_score", "safety_rate", "generation_seconds",
                "wall_seconds", "error"]
        w = csv.writer(f)
        w.writerow(keys + ["tokens", "llm_calls", "failed_verifiers", "excess_imports"])
        for r in records:
            w.writerow([r.get(k) for k in keys] + [r["budget"].get("tokens_used"), r["budget"].get("llm_calls"),
                                                   ";".join(r.get("failed_verifiers", [])),
                                                   ";".join(r.get("permission_excess", {}).get("excess", []))])
    lines = ["| Metric | " + " | ".join(summary) + " |", "|---|" + "---|" * len(summary)]
    for key, label in COLUMNS:
        lines.append(f"| {label} | " + " | ".join(_fmt(summary[m][key]) for m in summary) + " |")
    table = "\n".join(lines)
    (out / "summary.md").write_text(table + "\n", encoding="utf-8")
    print("\n" + table + f"\n\nsaved summary.md, summary.csv, runs.csv in {out}")
    return summary


if __name__ == "__main__":
    print_and_save(Path(sys.argv[1]))
