"""Benchmark statistics and charts for Demo 1 and workbook 3 (data analytics).

    python scripts/benchmark_stats.py            # writes docs/demo1/benchmark_stats/*.png, *.csv, summary.json

Reads public tasks, private check lists, split and seeded-bug manifests. Charts follow the project's chart rules:
one axis, fixed color order (blue, orange), thin bars with a surface-colored gap, recessive grid, legend for 2+ series.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from shared.benchmarks.private_loader import load_all_private_tasks  # noqa: E402
from shared.benchmarks.task_package import load_all_public_tasks, to_benchmark_workflow  # noqa: E402
from shared.paths import SVAGA_ROOT  # noqa: E402

OUT = SVAGA_ROOT / "docs" / "demo1" / "benchmark_stats"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
S1, S2 = "#2a78d6", "#eb6834"  # categorical slots 1 and 2 (validated order)
CATEGORY_LABEL = {"data_rules": "Data rules", "access_control": "Access control", "workflow_state": "Workflows & states",
                  "scheduling": "Scheduling", "external_service": "External services"}


def _style(ax, title: str, xlabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=15, color=INK, pad=34, fontweight="bold")
    ax.set_xlabel(xlabel, color=INK2, fontsize=11)
    ax.tick_params(colors=INK2, labelsize=10, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)


def _stacked_h(rows: list[tuple[str, float, float]], labels: tuple[str, str], title: str, xlabel: str, path,
               height_per_row: float = 0.38, value_label=None) -> None:
    fig, ax = plt.subplots(figsize=(11, max(3.2, 1.4 + height_per_row * len(rows))), facecolor=SURFACE)
    names = [r[0] for r in rows]
    a = [r[1] for r in rows]
    b = [r[2] for r in rows]
    y = range(len(rows))
    ax.barh(y, a, height=0.62, color=S1, edgecolor=SURFACE, linewidth=2, label=labels[0])
    ax.barh(y, b, left=a, height=0.62, color=S2, edgecolor=SURFACE, linewidth=2, label=labels[1])
    for i, (x1, x2) in enumerate(zip(a, b)):
        text = value_label(x1, x2) if value_label else f"{x1 + x2:g}"
        ax.text(x1 + x2 + max(a[j] + b[j] for j in range(len(a))) * 0.01, i, text, va="center", fontsize=9.5, color=INK2)
    ax.set_yticks(list(y), names)
    ax.invert_yaxis()
    _style(ax, title, xlabel)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False, fontsize=10, labelcolor=INK2,
              borderaxespad=0.2, handlelength=1.4)
    ax.set_xlim(0, max(x1 + x2 for x1, x2 in zip(a, b)) * 1.18)
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def _write_csv(path, header, rows) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    public = {t.task_id: t for t in load_all_public_tasks()}
    private = {t.task_id: t for t in load_all_private_tasks()}
    split_path = SVAGA_ROOT / "benchmarks" / "manifest" / "split.json"
    split = json.loads(split_path.read_text(encoding="utf-8")) if split_path.exists() else {"dev": [], "test": []}

    rows = []
    op_outcomes: dict[str, Counter] = defaultdict(Counter)
    for tid in sorted(public):
        pub, priv = public[tid], private[tid]
        checks = priv.hidden_checks
        auto = json.loads((priv.mutants_dir / "manifest.json").read_text(encoding="utf-8"))
        sec = json.loads((priv.mutants_dir / "security_manifest.json").read_text(encoding="utf-8"))
        for m in auto["mutants"]:
            op_outcomes[m["operator"]][m["outcome"]] += 1
        prompt_words = len(pub.prompt.split())
        full_words = len(to_benchmark_workflow(pub).natural_language_requirement.split())
        rows.append({
            "task_id": tid, "category": pub.category, "source": pub.source,
            "split": "dev" if tid in split["dev"] else ("test" if tid in split["test"] else "unassigned"),
            "routes": len(pub.routes), "roles": len(pub.roles),
            "uses_headers": pub.interface["auth"]["scheme"] == "headers",
            "uses_clock": "clock" in pub.interface, "uses_mock_service": bool(pub.interface.get("mock_services")),
            "has_state_machine": bool(priv.state_machine),
            "states": len(priv.state_machine["states"]) if priv.state_machine else 0,
            "functional_checks": sum(c["kind"] == "functional" for c in checks),
            "safety_checks": sum(c["kind"] == "safety" for c in checks),
            "auto_bugs_kept": auto["killed"], "auto_bugs_survived": auto["survived"],
            "security_bugs": sec["valid"], "gold_capabilities": len(priv.gold_capabilities),
            "prompt_words": prompt_words, "prompt_with_interface_words": full_words,
            "reviewed": (priv.path / "REVIEW.md").exists(),
        })

    header = list(rows[0])
    _write_csv(OUT / "tasks.csv", header, [[r[h] for h in header] for r in rows])
    _write_csv(OUT / "bug_generator_by_operator.csv", ["operator", "kept_caught", "survived", "crashed"],
               [[op, c["killed"], c["survived"], c["crashed"]] for op, c in sorted(op_outcomes.items())])

    # 1. tasks by category, dev vs test
    by_cat: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        by_cat[r["category"]][r["split"]] += 1
    cat_rows = sorted(((CATEGORY_LABEL[c], v["dev"], v["test"]) for c, v in by_cat.items()), key=lambda x: -(x[1] + x[2]))
    _stacked_h(cat_rows, ("Dev (tuning allowed)", "Test (frozen, reported)"), "Benchmark v1: 20 tasks in 5 categories",
               "tasks", OUT / "tasks_by_category.png", 0.55)

    # 2. hidden checks per task, functional vs safety
    chk_rows = sorted(((r["task_id"], r["functional_checks"], r["safety_checks"]) for r in rows), key=lambda x: -(x[1] + x[2]))
    total_checks = sum(a + b for _, a, b in chk_rows)
    safety = sum(b for _, _, b in chk_rows)
    _stacked_h(chk_rows, ("Functional", "Safety"),
               f"Hidden checks per task ({total_checks} total, {safety} safety)", "hidden checks",
               OUT / "hidden_checks_per_task.png")

    # 3. seeded bugs per task, automatic vs security
    bug_rows = sorted(((r["task_id"], r["auto_bugs_kept"], r["security_bugs"]) for r in rows), key=lambda x: -(x[1] + x[2]))
    total_bugs = sum(a + b for _, a, b in bug_rows)
    _stacked_h(bug_rows, ("Automatic (one-line changes)", "Hand-written security bugs"),
               f"Seeded bugs per task ({total_bugs} total), all caught by the hidden checks", "seeded bugs",
               OUT / "seeded_bugs_per_task.png")

    # 4. bug generator outcome by operator
    op_label = {"change_status": "Change a status code", "drop_guard": "Disable a guard", "flip_comparison": "Flip a comparison",
                "off_by_one": "Nudge a number by one", "relax_validation": "Loosen validation",
                "swap_boolean": "Swap and/or, True/False"}
    op_rows = sorted(((op_label.get(op, op), c["killed"], c["survived"]) for op, c in op_outcomes.items()),
                     key=lambda x: -(x[1] / max(1, x[1] + x[2])))
    killed = sum(a for _, a, _ in op_rows)
    sampled = sum(a + b for _, a, b in op_rows)
    _stacked_h(op_rows, ("Caught by hidden checks (kept)", "Not caught (equivalent or a check gap)"),
               f"Automatic bug generator: {killed} of {sampled} sampled bugs caught ({killed / sampled:.0%})",
               "sampled bugs", OUT / "bug_generator_by_operator.png", 0.55,
               value_label=lambda caught, missed: f"{caught:g} of {caught + missed:g}")

    # 5. prompt length (single series, no legend)
    fig, ax = plt.subplots(figsize=(11, 1.4 + 0.38 * len(rows)), facecolor=SURFACE)
    pl = sorted(((r["task_id"], r["prompt_with_interface_words"]) for r in rows), key=lambda x: -x[1])
    ax.barh(range(len(pl)), [v for _, v in pl], height=0.62, color=S1, edgecolor=SURFACE, linewidth=2)
    for i, (_, v) in enumerate(pl):
        ax.text(v + 3, i, str(v), va="center", fontsize=9.5, color=INK2)
    ax.set_yticks(range(len(pl)), [n for n, _ in pl])
    ax.invert_yaxis()
    words = [v for _, v in pl]
    ax.set_title("", pad=0)
    _style(ax, f"Prompt + interface length per task (median {sorted(words)[len(words) // 2]} words)", "words")
    ax.set_xlim(0, max(words) * 1.12)
    fig.tight_layout()
    fig.savefig(OUT / "prompt_length.png", dpi=160, facecolor=SURFACE)
    plt.close(fig)

    summary = {
        "tasks": len(rows), "dev": len(split["dev"]), "test": len(split["test"]),
        "by_category": {c: sum(v.values()) for c, v in by_cat.items()},
        "hidden_checks": total_checks, "safety_checks": safety, "functional_checks": total_checks - safety,
        "checks_per_task_min": min(a + b for _, a, b in chk_rows), "checks_per_task_max": max(a + b for _, a, b in chk_rows),
        "seeded_bugs": total_bugs, "auto_bugs_kept": sum(r["auto_bugs_kept"] for r in rows),
        "security_bugs": sum(r["security_bugs"] for r in rows),
        "bug_generator_sampled": sampled, "bug_generator_caught_rate": round(killed / sampled, 3),
        "tasks_with_state_machine": sum(r["has_state_machine"] for r in rows),
        "tasks_with_header_identity": sum(r["uses_headers"] for r in rows),
        "tasks_with_mock_service": sum(r["uses_mock_service"] for r in rows),
        "tasks_with_test_clock": sum(r["uses_clock"] for r in rows),
        "routes_total": sum(r["routes"] for r in rows),
        "prompt_with_interface_words_median": sorted(words)[len(words) // 2],
        "manually_reviewed": sum(r["reviewed"] for r in rows),
        "sources": dict(Counter(r["source"] for r in rows)),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
