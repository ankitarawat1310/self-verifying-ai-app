"""Validate benchmark v1 tasks with the independent judge.

For each task:
  1. the reference app must pass 100% of hidden checks;
  2. an empty stub app must fail every hidden check (no check passes by doing nothing);
  3. (optional, --repeat N) the reference result must be identical across N runs (no flaky checks).

Usage:
    python scripts/validate_benchmark.py                 # all tasks
    python scripts/validate_benchmark.py crud_contact_directory approval_leave_request --repeat 3
    python scripts/validate_benchmark.py --json results/benchmark_validation.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.benchmarks.private_loader import load_all_private_tasks, load_private_task
from svaga_platform.app.judge import judge_candidate

STUB_APP = "from fastapi import FastAPI\napp = FastAPI()\n"


def validate(task_id: str, repeat: int) -> dict:
    private = load_private_task(task_id)
    reference_code = private.reference_app.read_text(encoding="utf-8")
    runs = [judge_candidate(task_id, reference_code) for _ in range(max(1, repeat))]
    ref = runs[0]
    stub = judge_candidate(task_id, STUB_APP)
    signatures = {tuple((c.id, c.passed) for c in r.checks) for r in runs}
    auto_path, sec_path = private.mutants_dir / "manifest.json", private.mutants_dir / "security_manifest.json"
    auto = json.loads(auto_path.read_text(encoding="utf-8")) if auto_path.exists() else {"killed": 0, "sampled": 0}
    sec = json.loads(sec_path.read_text(encoding="utf-8")) if sec_path.exists() else {"valid": 0, "total": 0}
    report = {
        "task_id": task_id,
        "checks": len(private.hidden_checks),
        "safety_checks": sum(1 for c in private.hidden_checks if c["kind"] == "safety"),
        "reference_passed": ref.passed_count,
        "reference_ok": ref.passed,
        "reference_failures": [{"id": c.id, "detail": c.detail} for c in ref.checks if not c.passed],
        "reference_error": ref.error,
        "stub_passed": stub.passed_count,
        "stub_passing_checks": [c.id for c in stub.checks if c.passed],
        "deterministic": len(signatures) == 1,
        "seeded_bugs_kept": auto["killed"],
        "seeded_bugs_sampled": auto["sampled"],
        "security_bugs_valid": sec["valid"],
        "security_bugs_total": sec["total"],
        "reviewed": (private.path / "REVIEW.md").exists(),
        "seconds": ref.seconds,
    }
    report["valid"] = (report["reference_ok"] and report["stub_passed"] == 0 and report["deterministic"]
                       and report["checks"] >= 10 and report["seeded_bugs_kept"] >= 5
                       and report["security_bugs_total"] >= 3
                       and report["security_bugs_valid"] == report["security_bugs_total"])
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tasks", nargs="*")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    task_ids = args.tasks or [t.task_id for t in load_all_private_tasks()]
    reports = []
    for task_id in task_ids:
        r = validate(task_id, args.repeat)
        reports.append(r)
        flag = "VALID  " if r["valid"] else "INVALID"
        print(f"{flag} {task_id:32} checks={r['checks']:2} (safety {r['safety_checks']:2})  "
              f"reference {r['reference_passed']}/{r['checks']}  stub {r['stub_passed']}/{r['checks']}  "
              f"deterministic={r['deterministic']}  bugs={r['seeded_bugs_kept']}+sec {r['security_bugs_valid']}/"
              f"{r['security_bugs_total']}  {'reviewed' if r['reviewed'] else 'not reviewed'}")
        for f in r["reference_failures"]:
            print(f"        reference failed {f['id']}: {f['detail']}")
        if r["reference_error"]:
            print(f"        error: {r['reference_error']}")
        if r["stub_passing_checks"]:
            print(f"        stub passed (vacuous?): {r['stub_passing_checks']}")
        if r["checks"] < 10:
            print("        fewer than 10 hidden checks")
        if r["seeded_bugs_kept"] < 5:
            print("        fewer than 5 seeded bugs kept: run scripts/generate_mutants.py")
        if r["security_bugs_valid"] != r["security_bugs_total"] or r["security_bugs_total"] < 3:
            print("        security bugs missing or not all caught: run scripts/build_security_mutants.py")
    valid = sum(r["valid"] for r in reports)
    reviewed = sum(r["reviewed"] for r in reports)
    print(f"\n{valid}/{len(reports)} tasks valid; {reviewed}/{len(reports)} manually reviewed; "
          f"{sum(r['checks'] for r in reports)} hidden checks; "
          f"{sum(r['seeded_bugs_kept'] + r['security_bugs_valid'] for r in reports)} seeded bugs")
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as fh:
            json.dump(reports, fh, indent=2)
    return 0 if valid == len(reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
