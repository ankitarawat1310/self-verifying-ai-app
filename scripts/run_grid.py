"""Run the experiment grid: models x tasks x repeats, then print the summary table.

    python scripts/run_grid.py --split dev --name smoke            # Day 8: M0, M1, M2 on the 5 dev tasks, 1 repeat
    python scripts/run_grid.py --split test --repeats 3 --name demo1   # Day 9: needs a frozen, unchanged benchmark

Results go to results/grid/<name>/. Re-running the same command resumes: finished runs are skipped.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.llm.provider import describe_llm_provider  # noqa: E402
from svaga_platform.app.experiments.grid import run_one  # noqa: E402
from scripts.summarize_grid import print_and_save  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["m0", "m1", "m2"])
    ap.add_argument("--split", choices=["dev", "test"], default="dev")
    ap.add_argument("--tasks", nargs="*", help="override the split's task list")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--name", default=time.strftime("%Y%m%d_%H%M%S"))
    ap.add_argument("--no-recall", action="store_true", help="skip running each model's tests against seeded bugs")
    ap.add_argument("--allow-scripted", action="store_true")
    args = ap.parse_args()

    who = describe_llm_provider()
    print(f"model: {who['provider']} / {who['model']}")
    if who["provider"] == "scripted" and not args.allow_scripted:
        print("Refusing to run with the scripted stand-in. Set SVAGA_LLM_PROVIDER=ollama and clear SVAGA_SCRIPTED_LLM.")
        return 2
    if args.split == "test" and not args.tasks:
        check = subprocess.run([sys.executable, str(ROOT / "scripts" / "freeze_benchmark.py"), "check"],
                               capture_output=True, text=True)
        print(check.stdout.strip())
        if check.returncode != 0:
            print("The test split only runs on a frozen, unchanged benchmark.")
            return 1

    split = json.loads((ROOT / "benchmarks" / "manifest" / "split.json").read_text(encoding="utf-8"))
    tasks = args.tasks or split[args.split]
    out = ROOT / "results" / "grid" / args.name
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.json").write_text(json.dumps({"models": args.models, "tasks": tasks, "repeats": args.repeats,
                                                 "split": args.split, "llm": who}, indent=2), encoding="utf-8")
    total = len(args.models) * len(tasks) * args.repeats
    n = 0
    started = time.monotonic()
    # repeat-major order: if the night runs out, every model has the same number of complete repeats
    for repeat in range(1, args.repeats + 1):
        for task in tasks:
            for model in args.models:
                n += 1
                rec = run_one(model, task, repeat, out, recall=not args.no_recall, llm_label=who)
                recall = rec.get("violation_recall")
                print(f"[{n}/{total}] {model} {task} r{repeat}: {rec['decision']:6s} hidden {rec['hidden_passed']}/"
                      f"{rec['hidden_total']}  recall {recall if recall is not None else '-'}  "
                      f"{rec['wall_seconds']}s  (elapsed {round((time.monotonic() - started) / 60, 1)} min)",
                      flush=True)
    print_and_save(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
