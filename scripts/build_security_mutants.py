"""Apply hand-written security bugs (mutants/security.yaml) to each reference app and classify them with the judge.

    python scripts/build_security_mutants.py                 # all tasks
    python scripts/build_security_mutants.py login_lockout

A security bug is valid when it is caught (killed) AND at least one of its expected checks is among the failures.
Writes mutants/sec_<id>.py for caught bugs and mutants/security_manifest.json with every outcome.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.benchmarks.private_loader import load_all_private_tasks, load_private_task
from svaga_platform.app.judge import judge_candidate


def apply_edits(source: str, edits: list[dict]) -> str:
    text = source.replace("\r\n", "\n")
    for edit in edits:
        find, replace, occurrence = edit["find"], edit["replace"], int(edit.get("occurrence", 1))
        index = -1
        for _ in range(occurrence):
            index = text.find(find, index + 1)
            if index < 0:
                raise ValueError(f"edit target not found (occurrence {occurrence}): {find[:80]!r}")
        text = text[:index] + replace + text[index + len(find):]
    return text


def run(task_id: str) -> dict:
    private = load_private_task(task_id)
    spec_path = private.mutants_dir / "security.yaml"
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    reference = private.reference_app.read_text(encoding="utf-8")
    check_ids = {c["id"] for c in private.hidden_checks}
    for old in private.mutants_dir.glob("sec_*.py"):
        old.unlink()
    entries = []
    for bug in spec["security_mutants"]:
        entry = {"id": bug["id"], "description": bug["description"], "expected_failing_checks": bug["expected_failing_checks"]}
        unknown = sorted(set(bug["expected_failing_checks"]) - check_ids)
        try:
            source = apply_edits(reference, bug["edits"])
        except ValueError as error:
            entries.append({**entry, "outcome": "edit_failed", "error": str(error), "valid": False})
            continue
        result = judge_candidate(task_id, source, startup_timeout=15)
        failed = [c.id for c in result.checks if not c.passed]
        outcome = "crashed" if not result.started else ("killed" if failed else "survived")
        hit = sorted(set(failed) & set(bug["expected_failing_checks"]))
        entry.update({"outcome": outcome, "killed_by": failed, "expected_hit": hit, "unknown_expected": unknown,
                      "valid": outcome == "killed" and bool(hit) and not unknown})
        entries.append(entry)
        if outcome == "killed":
            (private.mutants_dir / f"{bug['id']}.py").write_text(source, encoding="utf-8")
    manifest = {"task_id": task_id, "total": len(entries), "valid": sum(e["valid"] for e in entries), "mutants": entries}
    (private.mutants_dir / "security_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tasks", nargs="*")
    args = parser.parse_args()
    ok = True
    for task_id in args.tasks or [t.task_id for t in load_all_private_tasks()]:
        m = run(task_id)
        print(f"{task_id:32} security bugs valid {m['valid']}/{m['total']}", flush=True)
        for e in m["mutants"]:
            if not e["valid"]:
                ok = False
                detail = e.get("error") or f"outcome={e['outcome']} expected={e['expected_failing_checks']} failed={e.get('killed_by')}"
                print(f"      PROBLEM {e['id']}: {detail}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
