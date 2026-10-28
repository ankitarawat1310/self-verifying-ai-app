"""Read-only candidate screening, not proof of contamination-free training data.

Downloads only pinned benchmark instructions into an audit-only directory.
Never downloads oracle answers or executes dataset content.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen


def grams(text):
    words = re.findall(r"[a-z0-9_]+", text.lower())
    return {tuple(words[i:i + 5]) for i in range(len(words) - 4)}


def description(row):
    if isinstance(row.get("instruction"), str) and row["instruction"].strip():
        return row["instruction"]
    for message in row.get("conversations") or []:
        if message.get("role") == "user":
            return message.get("content", "").split("Task Description:", 1)[-1].split("Current terminal state:", 1)[0].strip()
    return ""


def make_index(instructions):
    sets = {key: grams(value) for key, value in instructions.items()}
    index = defaultdict(set)
    for key, items in sets.items():
        for item in items:
            index[item].add(key)
    return sets, index


def screen(row, sets, index):
    task = str(row.get("task") or "")
    group = re.sub(r"_copy\d+$", "", task)
    hits = []
    if group in sets:
        hits.append({"benchmark_task": group, "reason": "exact_task_id"})
    text = description(row)
    candidate = grams(text)
    counts = Counter(key for gram in candidate for key in index.get(gram, ()))
    for key, common in counts.items():
        denominator = min(len(candidate), len(sets[key]))
        score = common / denominator if denominator else 0
        if common >= 10 and score >= 0.5:
            hits.append({"benchmark_task": key, "reason": "instruction_5gram_overlap",
                         "shared_5grams": common, "containment": round(score, 4)})
    return hits, bool(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path)
    source.add_argument("--dataset")
    parser.add_argument("--revision")
    parser.add_argument("--inventory", type=Path, default=Path(__file__).with_name("terminal_bench_2_1.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.dataset and not re.fullmatch(r"[0-9a-f]{40}", args.revision or ""):
        parser.error("Dataset mode requires a pinned 40-character --revision")
    if args.output_dir.exists():
        parser.error("Use a new output directory; existing audit evidence is preserved")
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    ids = inventory["task_ids"]
    assert len(ids) == len(set(ids)) == inventory["task_count"]
    revision = inventory["revision"]
    assert re.fullmatch(r"[0-9a-f]{40}", revision)

    def fetch(task):
        assert re.fullmatch(r"[a-z0-9.-]+", task)
        url = f"https://raw.githubusercontent.com/harbor-framework/terminal-bench-2-1/{revision}/tasks/{task}/instruction.md"
        with urlopen(Request(url, headers={"User-Agent": "SVAGA-data-audit"}), timeout=60) as response:
            data = response.read()
        return task, data.decode("utf-8"), hashlib.sha256(data).hexdigest()

    with ThreadPoolExecutor(max_workers=6) as pool:
        fetched = list(pool.map(fetch, ids))
    instructions = {key: text for key, text, digest in fetched}
    sets, index = make_index(instructions)
    print(f"Loaded {len(instructions)} pinned benchmark instructions", flush=True)
    args.output_dir.mkdir(parents=True)
    # Audit-only material. Never feed this directory to a trainer or RAG index.
    (args.output_dir / "benchmark-instructions.audit-only.json").write_text(
        json.dumps(instructions, indent=2), encoding="utf-8")
    if args.input:
        def local_rows():
            with args.input.open(encoding="utf-8") as stream:
                for line in stream:
                    if line.strip():
                        yield json.loads(line)
        rows = local_rows()
        source_info = {"path": str(args.input.resolve()), "sha256": hashlib.sha256(args.input.read_bytes()).hexdigest()}
    else:
        from datasets import load_dataset
        rows = load_dataset(args.dataset, revision=args.revision, split="train", streaming=True)
        source_info = {"dataset": args.dataset, "revision": args.revision, "split": "train"}
    flags, total, missing = [], 0, 0
    for total, row in enumerate(rows, 1):
        matches, has_text = screen(row, sets, index)
        missing += not has_text
        if matches:
            flags.append({"record_number": total, "task": row.get("task"),
                          "decision": "quarantine_pending_review", "matches": matches})
        if total % 1000 == 0:
            print(f"Screened {total}; flagged {len(flags)}", flush=True)
    report = {"status": "screening_complete_not_training_approval", "source": source_info,
              "benchmark_revision": revision, "benchmark_tasks": len(ids),
              "instruction_sha256": {key: digest for key, text, digest in fetched},
              "records_screened": total, "missing_descriptions": missing, "flagged_records": len(flags),
              "flags": flags, "method": "Exact task IDs after removing _copy suffix; instruction token 5-gram containment >= 0.5 with >= 10 shared grams.",
              "limitations": ["Heuristic screening, not semantic duplicate detection.",
                              "Renamed/paraphrased tasks and solution-only leakage may be missed.",
                              "Does not scan full assistant/tool trajectories or base-model pretraining.",
                              "No outcome verification, licence approval or train/validation split performed.",
                              "Zero flags does not establish contamination-free data."]}
    (args.output_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "records_screened", "missing_descriptions", "flagged_records")}), flush=True)


if __name__ == "__main__":
    main()
