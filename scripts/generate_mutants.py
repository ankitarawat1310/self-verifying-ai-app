"""Generate seeded bugs (mutants) for benchmark tasks and classify them with the independent judge.

    python scripts/generate_mutants.py                       # all tasks, up to 12 sampled mutants each
    python scripts/generate_mutants.py room_booking --max 20 --seed 7

Writes benchmarks/<private>/<task>/mutants/: one file per kept (killed) mutant plus manifest.json listing every
sampled mutant with its outcome (killed / survived / crashed) and the checks that caught it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.benchmarks.private_loader import load_all_private_tasks, load_private_task
from svaga_platform.app.judge import judge_candidate
from svaga_platform.app.judge.mutation import generate_candidates, sample_candidates


def run(task_id: str, limit: int, seed: int) -> dict:
    private = load_private_task(task_id)
    source = private.reference_app.read_text(encoding="utf-8")
    candidates = generate_candidates(source)
    sampled = sample_candidates(candidates, limit, seed)
    out_dir = private.mutants_dir
    out_dir.mkdir(exist_ok=True)
    for old in out_dir.glob("auto_*.py"):
        old.unlink()
    entries = []
    for m in sampled:
        result = judge_candidate(task_id, m.source, startup_timeout=15)
        failed = [c.id for c in result.checks if not c.passed]
        outcome = "crashed" if not result.started else ("killed" if failed else "survived")
        entry = {"id": f"auto_{m.mutant_id}", "operator": m.operator, "line": m.lineno, "description": m.description,
                 "outcome": outcome, "killed_by": failed, "checks_failed": len(failed),
                 "checks_total": len(result.checks)}
        entries.append(entry)
        if outcome == "killed":
            (out_dir / f"{entry['id']}.py").write_text(m.source, encoding="utf-8")
    manifest = {"task_id": task_id, "seed": seed, "candidates": len(candidates), "sampled": len(sampled),
                "killed": sum(e["outcome"] == "killed" for e in entries),
                "survived": sum(e["outcome"] == "survived" for e in entries),
                "crashed": sum(e["outcome"] == "crashed" for e in entries), "mutants": entries}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tasks", nargs="*")
    parser.add_argument("--max", type=int, default=12)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    for task_id in args.tasks or [t.task_id for t in load_all_private_tasks()]:
        m = run(task_id, args.max, args.seed)
        print(f"{task_id:32} candidates={m['candidates']:3} sampled={m['sampled']:2} killed={m['killed']:2} "
              f"survived={m['survived']:2} crashed={m['crashed']:2}", flush=True)
        for e in m["mutants"]:
            if e["outcome"] == "survived":
                print(f"      survived: {e['id']} line {e['line']}: {e['description']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
