"""Experiment grid: models x tasks x repeats, each run generated, self-verified, judged and scored.

Judge-side code (reads benchmarks/private). Pipelines never import this module.
Each run writes <out>/<model>/<task>/r<repeat>/: the generated files, verification.json, judge.json and
record.json. A run whose record.json exists is skipped, so an interrupted overnight run resumes where it stopped.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from shared.benchmarks.task_package import find_benchmark
from shared.budget.tracker import BudgetProfile, BudgetTracker
from shared.paths import TASKS_PRIVATE_DIR
from svaga_platform.app.experiments.metrics import permission_excess, run_flags

ROOT = Path(__file__).resolve().parents[3]
# One budget for every model (plan section 9c, Day 8): 8 LLM calls, 40K tokens, 180 s of verification.
DEMO1_BUDGET = BudgetProfile(max_llm_calls=8, max_tokens=40_000, max_verification_seconds=180.0, max_repair_rounds=0)
CODE_DIRS = ["svaga_platform/app/pipelines", "svaga_platform/app/spec_first", "svaga_platform/app/verification",
             "svaga_platform/app/artifacts.py", "svaga_platform/app/release_gate.py", "shared",
             "model1_rag_generator/backend/app"]


def code_hash() -> str:
    """Hash of the code that decides a run's outcome (CRLF-normalized), recorded so runs can be compared."""
    h = hashlib.sha256()
    for rel in CODE_DIRS:
        p = ROOT / rel
        files = [p] if p.is_file() else sorted(x for x in p.rglob("*.py") if "__pycache__" not in x.parts)
        for f in files:
            h.update(f.relative_to(ROOT).as_posix().encode())
            h.update(f.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def _pytest_failures(test_code: str, app_code: str, timeout: int = 120) -> tuple[set[str], int]:
    """Run a test file against one app; return (failing test names, number of tests that ran)."""
    with tempfile.TemporaryDirectory(prefix="svaga_recall_") as d:
        Path(d, "app.py").write_text(app_code, encoding="utf-8")
        Path(d, "test_app.py").write_text(test_code, encoding="utf-8")
        report = Path(d, "junit.xml")
        env = {**os.environ, "NO_NETWORK": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        try:
            subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:warnings",
                            f"--junitxml={report}", "test_app.py"], cwd=d, capture_output=True, text=True,
                           timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            return {"<timeout>"}, 0
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


def violation_recall(task_id: str, test_code: str, workers: int = 4) -> dict[str, Any]:
    """How many seeded bugs the model's own tests catch (only tests that pass on the reference app count)."""
    private = TASKS_PRIVATE_DIR / task_id
    ref_failed, ref_total = _pytest_failures(test_code, (private / "reference" / "app.py").read_text(encoding="utf-8"))
    usable = ref_total - len(ref_failed)
    mutants = sorted((private / "mutants").glob("*.py"))
    if usable <= 0 or not mutants:
        return {"recall": 0.0 if mutants else None, "caught": 0, "bugs": len(mutants), "tests_on_reference": ref_total,
                "tests_passing_on_reference": max(usable, 0)}

    def caught(m: Path) -> bool:
        failed, _ = _pytest_failures(test_code, m.read_text(encoding="utf-8"))
        return bool(failed - ref_failed)

    with ThreadPoolExecutor(workers) as ex:
        hits = list(ex.map(caught, mutants))
    return {"recall": round(sum(hits) / len(mutants), 4), "caught": sum(hits), "bugs": len(mutants),
            "tests_on_reference": ref_total, "tests_passing_on_reference": usable,
            "caught_ids": [m.stem for m, h in zip(mutants, hits) if h]}


def own_mutation_score(app_code: str, test_code: str, *, limit: int = 10, seed: int = 1, workers: int = 4) -> dict[str, Any]:
    """Classic mutation score: seed small bugs into the model's OWN app (same 6 operators as the benchmark) and count
    how many its own tests catch. Fair to every model, because the tests are judged against the code they were
    written for, including tests that reach into that app's internals."""
    from svaga_platform.app.judge.mutation import generate_candidates, sample_candidates

    base_failed, base_total = _pytest_failures(test_code, app_code)
    usable = base_total - len(base_failed)
    try:
        mutants = sample_candidates(generate_candidates(app_code), limit, seed)
    except SyntaxError:
        mutants = []
    if usable <= 0 or not mutants:
        return {"score": 0.0 if mutants else None, "killed": 0, "mutants": len(mutants), "tests": base_total,
                "tests_passing_on_own_app": max(usable, 0)}

    def killed(m) -> bool:
        failed, total = _pytest_failures(test_code, m.source)
        return total == 0 or bool(failed - base_failed)

    with ThreadPoolExecutor(workers) as ex:
        hits = list(ex.map(killed, mutants))
    return {"score": round(sum(hits) / len(mutants), 4), "killed": sum(hits), "mutants": len(mutants),
            "tests": base_total, "tests_passing_on_own_app": usable,
            "survivors": [f"{m.operator} line {m.lineno}: {m.description}" for m, h in zip(mutants, hits) if not h][:10]}


def run_one(model: str, task_id: str, repeat: int, out_root: Path, *, profile: BudgetProfile = DEMO1_BUDGET,
            recall: bool = True, llm_label: dict[str, str] | None = None) -> dict[str, Any]:
    from svaga_platform.app.judge.runner import judge_candidate
    from svaga_platform.app.pipelines.registry import get_pipeline

    run_dir = out_root / model / task_id / f"r{repeat}"
    rec_path = run_dir / "record.json"
    if rec_path.exists():
        return json.loads(rec_path.read_text(encoding="utf-8"))
    run_dir.mkdir(parents=True, exist_ok=True)
    os.environ["SVAGA_SEED"] = str(repeat)
    bench = find_benchmark(task_id)
    budget = BudgetTracker(profile=profile)
    started = time.monotonic()
    error = ""
    result = None
    try:
        result = get_pipeline(model).run(bench, budget=budget)
        decision = result.decision
    except Exception as exc:  # BudgetExceeded, provider errors, crashes: an ERROR is never an ACCEPT
        decision, error = "ERROR", f"{type(exc).__name__}: {exc}"
        (run_dir / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
    gen_seconds = time.monotonic() - started

    files = result.artifacts.to_files() if result else {}
    for name, content in files.items():
        (run_dir / name).write_text(content, encoding="utf-8")
    if result:
        (run_dir / "verification.json").write_text(json.dumps(result.verification, indent=2, default=str), encoding="utf-8")
        (run_dir / "metadata.json").write_text(json.dumps(result.metadata, indent=2, default=str), encoding="utf-8")
    app_code = result.artifacts.app_code if result else ""

    judged = judge_candidate(task_id, app_code) if app_code.strip() else None
    if judged:
        (run_dir / "judge.json").write_text(json.dumps(judged.to_dict(), indent=2, default=str), encoding="utf-8")
    checks = judged.checks if judged else []
    safety = [c for c in checks if c.kind == "safety"]
    flags = run_flags(decision, judged.passed_count if judged else None, len(checks) if judged else None)

    rec: dict[str, Any] = {
        "model": model, "task": task_id, "category": bench.category, "repeat": repeat,
        "decision": decision, "error": error,
        "hidden_passed": judged.passed_count if judged else 0, "hidden_total": len(checks),
        "safety_rate": (sum(c.passed for c in safety) / len(safety)) if safety else None,
        **flags,
        "failed_verifiers": [v["name"] for v in (result.verification.get("verifiers", []) if result else [])
                             if not v.get("passed")],
        "budget": budget.to_dict(), "generation_seconds": round(gen_seconds, 2),
        "permission_excess": permission_excess(app_code, calls_outside_service=bool(
            (bench.raw.get("interface") or {}).get("mock_services"))),
        "llm": llm_label or {}, "code_hash": code_hash(),
    }
    if recall and "test_app.py" in files and app_code.strip():
        r = violation_recall(task_id, files["test_app.py"])
        rec["violation_recall"], rec["recall_detail"] = r["recall"], r
        m = own_mutation_score(app_code, files["test_app.py"], seed=repeat)
        rec["own_mutation_score"], rec["own_mutation_detail"] = m["score"], m
    else:
        rec["violation_recall"] = rec["own_mutation_score"] = None
    rec["wall_seconds"] = round(time.monotonic() - started, 2)
    rec_path.write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
    return rec


def load_records(out_root: Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(out_root.rglob("record.json"))]
