"""Benchmark split and freeze.

    python scripts/freeze_benchmark.py split            # draw the dev/test split (seeded, one dev task per category)
    python scripts/freeze_benchmark.py freeze           # record SHA-256 of every benchmark file -> freeze.json
    python scripts/freeze_benchmark.py check            # exit 1 if any frozen file changed, was added or removed

Dev tasks may be used to tune prompts and retrieval. Test tasks are only run for reported numbers, and only after
`freeze`; `check` runs before every experiment so a result can never come from a benchmark that changed afterwards.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.benchmarks.task_package import load_all_public_tasks
from shared.paths import SVAGA_ROOT, TASK_SCHEMAS_DIR, TASKS_PRIVATE_DIR, TASKS_PUBLIC_DIR

MANIFEST_DIR = SVAGA_ROOT / "benchmarks" / "manifest"
SPLIT_PATH = MANIFEST_DIR / "split.json"
FREEZE_PATH = MANIFEST_DIR / "freeze.json"
SEED = 2026
FROZEN_ROOTS = [TASKS_PUBLIC_DIR, TASKS_PRIVATE_DIR, TASK_SCHEMAS_DIR,
                SVAGA_ROOT / "svaga_platform" / "app" / "judge"]
IGNORED_PARTS = {"__pycache__"}
IGNORED_NAMES = {"REVIEW.md"}  # review notes can keep changing without changing what is measured


def draw_split(seed: int = SEED) -> dict:
    rng = random.Random(seed)
    by_category: dict[str, list[str]] = {}
    for task in load_all_public_tasks():
        by_category.setdefault(task.category, []).append(task.task_id)
    dev = []
    for category in sorted(by_category):
        dev.append(rng.choice(sorted(by_category[category])))
    all_ids = sorted(t for ids in by_category.values() for t in ids)
    return {
        "seed": seed,
        "rule": "one dev task per category, drawn with random.Random(seed).choice over sorted task ids",
        "dev": sorted(dev),
        "test": [t for t in all_ids if t not in dev],
        "by_category": {c: sorted(ids) for c, ids in sorted(by_category.items())},
    }


def _files() -> list[Path]:
    out = []
    for root in FROZEN_ROOTS:
        for path in sorted(root.rglob("*")):
            if path.is_file() and not (set(path.parts) & IGNORED_PARTS) and path.name not in IGNORED_NAMES:
                out.append(path)
    return out


def _digest(path: Path) -> str:
    # Normalize line endings so a Windows checkout and a Linux checkout hash identically.
    data = path.read_bytes()
    if path.suffix in {".py", ".yaml", ".json", ".md", ".txt"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def snapshot() -> dict[str, str]:
    return {p.relative_to(SVAGA_ROOT).as_posix(): _digest(p) for p in _files()}


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "check"
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    if command == "split":
        split = draw_split()
        SPLIT_PATH.write_text(json.dumps(split, indent=2) + "\n", encoding="utf-8")
        print("dev :", ", ".join(split["dev"]))
        print("test:", ", ".join(split["test"]))
        return 0
    if command == "freeze":
        if not SPLIT_PATH.exists():
            print("draw the split first: python scripts/freeze_benchmark.py split")
            return 1
        files = snapshot()
        combined = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        FREEZE_PATH.write_text(json.dumps({
            "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "benchmark_hash": combined, "split": json.loads(SPLIT_PATH.read_text(encoding="utf-8")),
            "files": files}, indent=2) + "\n", encoding="utf-8")
        print(f"frozen {len(files)} files, benchmark hash {combined[:16]}")
        return 0
    if command == "check":
        if not FREEZE_PATH.exists():
            print("NOT FROZEN: no freeze.json yet (expected until just before the Day 9 test run)")
            return 1
        frozen = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
        now = snapshot()
        changed = sorted(k for k in frozen["files"] if k in now and now[k] != frozen["files"][k])
        removed = sorted(set(frozen["files"]) - set(now))
        added = sorted(set(now) - set(frozen["files"]))
        for label, items in (("changed", changed), ("removed", removed), ("added", added)):
            for item in items:
                print(f"{label}: {item}")
        if changed or removed or added:
            print("FROZEN BENCHMARK MODIFIED: results would not be comparable")
            return 1
        print(f"benchmark unchanged since {frozen['frozen_at']} (hash {frozen['benchmark_hash'][:16]})")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
