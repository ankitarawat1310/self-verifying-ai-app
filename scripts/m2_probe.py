"""Day 7 probe for M2 (spec-first) with the real model.

Default (spec only, about 1 LLM call per task): the model writes a BehaviorSpec for each dev task; the script shows
whether it passed the checks, what the spec contains, and whether the tests generated from it pass on the hidden
reference app (a failing test on the reference means the spec says something the task does not).
--bugs   also count how many seeded bugs the spec-generated tests catch (slower, no LLM calls).
--full   also run the whole M2 pipeline (spec + code) and score the app with the hidden judge.

Judge-side tool: it reads benchmarks/private, so it is never imported by a pipeline.

    python scripts/m2_probe.py                 # 5 dev tasks, spec only
    python scripts/m2_probe.py --bugs --full   # add bug catching and a full run
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from shared.budget.tracker import BudgetProfile, BudgetTracker  # noqa: E402
from shared.llm.provider import get_llm_provider  # noqa: E402
from shared.benchmarks.task_package import find_benchmark  # noqa: E402
from svaga_platform.app.spec_first.author import author_spec  # noqa: E402
from svaga_platform.app.spec_first.spec_tests import generate_spec_tests  # noqa: E402

PUBLIC, PRIVATE = ROOT / "benchmarks" / "public", ROOT / "benchmarks" / "private"


def run_pytest(src: str, app_code: str) -> tuple[set[str], int]:
    """Run the spec tests on one app; return (names of failing tests, total tests run)."""
    import xml.etree.ElementTree as ET

    with tempfile.TemporaryDirectory() as d:
        Path(d, "app.py").write_text(app_code, encoding="utf-8")
        Path(d, "test_app.py").write_text(src, encoding="utf-8")
        report = Path(d, "junit.xml")
        subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:warnings",
                        f"--junitxml={report}", "test_app.py"], cwd=d, capture_output=True, text=True, timeout=180)
        if not report.exists():
            return {"<collection failed>"}, 0
        failed, total = set(), 0
        for case in ET.parse(report).getroot().iter("testcase"):
            if case.find("skipped") is not None:
                continue
            total += 1
            if case.find("failure") is not None or case.find("error") is not None:
                failed.add(case.get("name", ""))
        return failed, total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", nargs="*")
    ap.add_argument("--bugs", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--allow-scripted", action="store_true", help="allow the offline stand-in model (for testing)")
    args = ap.parse_args()
    from shared.llm.provider import describe_llm_provider

    who = describe_llm_provider()
    print(f"model: {who['provider']} / {who['model']}")
    if who["provider"] == "scripted" and not args.allow_scripted:
        print("Refusing to run with the scripted stand-in. Set SVAGA_LLM_PROVIDER=ollama and clear SVAGA_SCRIPTED_LLM.")
        return 2
    tasks = args.tasks or json.loads((ROOT / "benchmarks" / "manifest" / "split.json").read_text())["dev"]
    out = ROOT / "results" / "m2_probe" / time.strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    llm = get_llm_provider()
    rows = []
    for task in tasks:
        interface = yaml.safe_load((PUBLIC / task / "task.yaml").read_text(encoding="utf-8"))["interface"]
        bench = find_benchmark(task)
        budget = BudgetTracker(profile=BudgetProfile(max_llm_calls=20))
        t0 = time.monotonic()
        spec, meta = author_spec(llm, task, bench.natural_language_requirement, interface, budget=budget)
        spec_s = time.monotonic() - t0
        src, summary = generate_spec_tests(spec, interface)
        (out / f"{task}.spec.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")
        (out / f"{task}.tests.py").write_text(src, encoding="utf-8")
        (out / f"{task}.checks.json").write_text(json.dumps(meta["history"], indent=2), encoding="utf-8")
        ref_failed, ref_total = run_pytest(src, (PRIVATE / task / "reference" / "app.py").read_text(encoding="utf-8"))
        ref_ok = ref_total - len(ref_failed)
        row = {"task": task, "source": meta["source"], "attempts": meta["attempts"], "spec_seconds": round(spec_s, 1),
               "state_machines": len(spec.state_machines), "rules": sum(len(o.rules) for o in spec.operations),
               "transitions": sum(len(o.transitions) for o in spec.operations), "cases": summary["cases"],
               "ref_pass": f"{ref_ok}/{ref_total}", "false_alarms": sorted(ref_failed)[:5],
               "first_errors": meta["history"][0]["report"]["errors"][:3]}
        if args.bugs:
            muts = sorted((PRIVATE / task / "mutants").glob("*.py"))
            # a bug counts as caught only if a test that PASSES on the reference fails on the buggy app
            caught = sum(1 for m in muts if run_pytest(src, m.read_text(encoding="utf-8"))[0] - ref_failed)
            row["bugs_caught"] = f"{caught}/{len(muts)}"
        if args.full:
            from svaga_platform.app.judge.runner import judge_candidate
            from svaga_platform.app.pipelines.m2_spec_first import M2SpecFirstPipeline

            t0 = time.monotonic()
            res = M2SpecFirstPipeline().run(bench, budget=BudgetTracker(profile=BudgetProfile(max_llm_calls=20)))
            judged = judge_candidate(task, res.artifacts.app_code) if res.artifacts.app_code else None
            failed_verifiers = [v["name"] for v in res.verification.get("verifiers", []) if not v.get("passed")]
            (out / f"{task}.verification.json").write_text(json.dumps(res.verification, indent=2, default=str), encoding="utf-8")
            if judged:
                (out / f"{task}.judge.json").write_text(json.dumps(judged.to_dict(), indent=2, default=str), encoding="utf-8")
            row.update({"gate_failed": failed_verifiers, "decision": res.decision, "hidden": f"{judged.passed_count}/{len(judged.checks)}" if judged else "no code",
                        "full_seconds": round(time.monotonic() - t0, 1)})
            (out / f"{task}.app.py").write_text(res.artifacts.app_code, encoding="utf-8")
        rows.append(row)
        print(json.dumps(row), flush=True)
    (out / "summary.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nsaved to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
