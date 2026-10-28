"""Day 10 analysis of a results/grid/<name> folder: confidence intervals, paired tests, failure taxonomy, charts.

    python scripts/analyze_grid.py results/grid/demo1

Writes <folder>/analysis/: analysis.md (tables for wb3 and slides), analysis.json, failure_taxonomy.csv and
charts/*.png. Reads only saved records and judge results; runs no model and no judge.

Statistics:
- 95% intervals by cluster bootstrap over tasks (10,000 resamples). The 3 repeats of a task are not independent, so
  whole tasks are resampled, keeping their repeats together.
- Paired model comparisons on the same (task, repeat) cells: exact McNemar test (two-sided binomial on the
  discordant pairs), for "passes all hidden checks" and for "shipped a broken app".
"""
from __future__ import annotations

import csv
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MODELS = ["m0", "m1", "m2"]
NAMES = {"m0": "M0 plain prompt", "m1": "M1 retrieval (RAG)", "m2": "M2 spec-first"}
# categorical slots 1-3 of the reference palette (validated all-pairs, light surface); color follows the model
COLOR = {"m0": "#2a78d6", "m1": "#eb6834", "m2": "#1baf7a"}
INK, INK2, MUTED, GRID, BASE, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
STATUS = {"good": "#0ca30c", "critical": "#d03b3b", "warning": "#fab219", "neutral": "#c3c2b7"}
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
N_BOOT = 10_000


# ---------------------------------------------------------------- loading
def load(folder: Path) -> list[dict]:
    recs = []
    for p in sorted(folder.glob("*/*/r*/record.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        j = p.parent / "judge.json"
        r["checks"] = json.loads(j.read_text(encoding="utf-8"))["checks"] if j.exists() else []
        meta = p.parent / "metadata.json"
        r["spec_source"] = json.loads(meta.read_text(encoding="utf-8")).get("spec_source") if meta.exists() else None
        r["shipped_broken"] = r["decision"] == "ACCEPT" and not r["hidden_pass"]
        recs.append(r)
    return recs


# ---------------------------------------------------------------- statistics
def _ratio(rs, num, den=None):
    d = [r for r in rs if den(r)] if den else rs
    return (sum(1 for r in d if num(r)) / len(d)) if d else None


METRICS = {
    "functional_pass": (lambda r: r["hidden_pass"], None),
    "hidden_check_rate": None,  # mean, handled separately
    "false_assurance_of_accepted": (lambda r: not r["hidden_pass"], lambda r: r["decision"] == "ACCEPT"),
    "shipped_broken_per_run": (lambda r: r["shipped_broken"], None),
    "false_rejection_of_rejected": (lambda r: r["hidden_pass"], lambda r: r["decision"] == "REJECT"),
    "benchmark_bug_recall": None,
    "own_mutation_score": None,
}


def metric_value(rs, name):
    if name == "hidden_check_rate":
        return sum(r["hidden_rate"] for r in rs) / len(rs) if rs else None
    if name in ("benchmark_bug_recall", "own_mutation_score"):
        key = "violation_recall" if name == "benchmark_bug_recall" else "own_mutation_score"
        vals = [r[key] for r in rs if r.get(key) is not None]
        return sum(vals) / len(vals) if vals else None
    num, den = METRICS[name]
    return _ratio(rs, num, den)


def cluster_bootstrap(rs, name, seed=2026):
    by_task = defaultdict(list)
    for r in rs:
        by_task[r["task"]].append(r)
    tasks = sorted(by_task)
    rng = random.Random(seed)
    vals = []
    for _ in range(N_BOOT):
        sample = [x for t in (rng.choice(tasks) for _ in tasks) for x in by_task[t]]
        v = metric_value(sample, name)
        if v is not None:
            vals.append(v)
    vals.sort()
    if not vals:
        return None, None
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def paired(records, a, b, outcome):
    cells = defaultdict(dict)
    for r in records:
        cells[(r["task"], r["repeat"])][r["model"]] = outcome(r)
    both = [v for v in cells.values() if a in v and b in v]
    only_a = sum(1 for v in both if v[a] and not v[b])
    only_b = sum(1 for v in both if v[b] and not v[a])
    return {"pairs": len(both), f"{a}_only": only_a, f"{b}_only": only_b, "p_value": round(mcnemar_exact(only_a, only_b), 4)}


# ---------------------------------------------------------------- failure taxonomy
TAXONOMY = [
    "App did not start",
    "Server crash (500) or no valid response",
    "Accepts invalid or unknown input (2xx, expected 422)",
    "Missing permission check (2xx, expected 403)",
    "Missing conflict or state rule (2xx, expected 409)",
    "Outside-service error not handled (expected 502)",
    "Identity treated as validation (422, expected 403)",
    "Rejects valid requests (4xx, expected 2xx)",
    "Wrong or missing route (404/405)",
    "Wrong response shape (missing key, wrong type)",
    "Other wrong status code",
    "Wrong value or state",
]


def classify(detail: str) -> str:
    d = detail or ""
    if "app did not start" in d:
        return TAXONOMY[0]
    if re.search(r"\b500\b|Internal Server Error|Connection reset|JSONDecodeError|ReadError|RemoteProtocolError", d):
        return TAXONOMY[1]
    m = re.search(r"assert \(?(\d{3}) == (\d{3})", d)
    if m:
        got, exp = int(m.group(1)), int(m.group(2))
        if exp == 502 or got == 502:
            return TAXONOMY[5]
        if got < 300 and exp == 422:
            return TAXONOMY[2]
        if got < 300 and exp == 403:
            return TAXONOMY[3]
        if got < 300 and exp == 409:
            return TAXONOMY[4]
        if got == 422 and exp == 403:
            return TAXONOMY[6]
        if got in (404, 405) and exp not in (404, 405):
            return TAXONOMY[8]
        if got >= 400 and exp < 300:
            return TAXONOMY[7]
        return TAXONOMY[10]
    if re.search(r"KeyError|TypeError|string indices|not subscriptable|AttributeError", d):
        return TAXONOMY[9]
    return TAXONOMY[11]


# ---------------------------------------------------------------- charts
def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(BASE)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def charts(records, stats, out: Path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "figure.facecolor": SURFACE, "savefig.facecolor": SURFACE})

    # 1. outcome of every run: shipped-correct / shipped-broken / rejected-correct / rejected-broken
    fig, ax = plt.subplots(figsize=(8, 2.8))
    segs = [("Shipped, correct", lambda r: r["decision"] == "ACCEPT" and r["hidden_pass"], STATUS["good"]),
            ("Shipped, broken (false assurance)", lambda r: r["shipped_broken"], STATUS["critical"]),
            ("Rejected, but correct", lambda r: r["decision"] != "ACCEPT" and r["hidden_pass"], STATUS["warning"]),
            ("Rejected, broken (caught)", lambda r: r["decision"] != "ACCEPT" and not r["hidden_pass"], STATUS["neutral"])]
    for i, m in enumerate(reversed(MODELS)):
        rs = [r for r in records if r["model"] == m]
        left = 0
        for label, fn, color in segs:
            n = sum(1 for r in rs if fn(r))
            if n:
                ax.barh(i, n, left=left, height=0.55, color=color, edgecolor=SURFACE, linewidth=2)
                ax.text(left + n / 2, i, str(n), ha="center", va="center", fontsize=9,
                        color="#ffffff" if color in (STATUS["good"], STATUS["critical"]) else INK)
            left += n
    ax.set_xlabel("runs (15 tasks x 3 repeats)", color=MUTED, fontsize=9)
    _style(ax)
    ax.set_yticks(range(len(MODELS)), [NAMES[m] for m in reversed(MODELS)], fontsize=9)
    ax.tick_params(axis="y", labelcolor=INK2)
    ax.yaxis.grid(False)
    ax.xaxis.grid(True, color=GRID, linewidth=0.6)
    from matplotlib.patches import Patch

    ax.legend(handles=[Patch(color=c, label=l) for l, _, c in segs], ncol=2, frameon=False, fontsize=8,
              loc="upper center", bbox_to_anchor=(0.5, -0.32), labelcolor=INK2)
    ax.set_title("What each model shipped, and whether it was really correct", loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(out / "1_outcomes.png", dpi=200)
    plt.close(fig)

    # 2. three headline rates with 95% cluster-bootstrap intervals (small multiples, one axis each)
    panels = [("functional_pass", "Passes every hidden check"),
              ("false_assurance_of_accepted", "Broken among shipped apps\n(false assurance, lower is better)"),
              ("benchmark_bug_recall", "Seeded bugs its own tests catch")]
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.4))
    for ax, (key, title) in zip(axes, panels):
        for i, m in enumerate(MODELS):
            s = stats[m][key]
            v, lo, hi = s["value"] or 0, s["ci_low"], s["ci_high"]
            ax.bar(i, v, width=0.5, color=COLOR[m])
            if lo is not None:
                ax.errorbar(i, v, yerr=[[v - lo], [hi - v]], color=INK2, capsize=4, linewidth=1)
            ax.text(i, (hi if hi is not None else v) + 0.03, f"{v:.0%}", ha="center", fontsize=9, color=INK)
        ax.set_xticks(range(3), ["M0", "M1", "M2"], color=INK2)
        ax.set_ylim(0, 1.12)
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
        ax.set_title(title, fontsize=9.5, color=INK, loc="left")
        _style(ax)
    fig.suptitle("Demo 1 results with 95% intervals (qwen3-coder:30b, 45 runs per model)", x=0.01, ha="left",
                 fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(out / "2_headline_rates.png", dpi=200)
    plt.close(fig)

    # 3. functional pass by task category (sequential blue, numbers in cells)
    cats = sorted({r["category"] for r in records})
    fig, ax = plt.subplots(figsize=(7, 2.6))
    for yi, m in enumerate(MODELS):
        for xi, c in enumerate(cats):
            rs = [r for r in records if r["model"] == m and r["category"] == c]
            v = sum(r["hidden_pass"] for r in rs) / len(rs) if rs else 0
            color = SEQ[min(len(SEQ) - 1, int(v * (len(SEQ) - 1) + 0.5))] if v > 0 else "#f0efec"
            ax.add_patch(matplotlib.patches.Rectangle((xi, yi), 0.96, 0.9, color=color))
            ax.text(xi + 0.48, yi + 0.45, f"{sum(r['hidden_pass'] for r in rs)}/{len(rs)}", ha="center", va="center",
                    fontsize=9, color="#ffffff" if v >= 0.5 else INK)
    ax.set_xlim(0, len(cats))
    ax.set_ylim(0, 3)
    ax.invert_yaxis()
    ax.set_xticks([i + 0.48 for i in range(len(cats))], [c.replace("_", " ") for c in cats], fontsize=8.5, color=INK2)
    ax.set_yticks([i + 0.45 for i in range(3)], [NAMES[m] for m in MODELS], fontsize=8.5, color=INK2)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    ax.set_title("Apps passing every hidden check, by task category", loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(out / "3_pass_by_category.png", dpi=200)
    plt.close(fig)

    # 4. failure taxonomy: failed hidden checks by cause (grouped horizontal bars, legend + labels)
    counts = {m: Counter(classify(c["detail"]) for r in records if r["model"] == m for c in r["checks"] if not c["passed"])
              for m in MODELS}
    kinds = [k for k in TAXONOMY if any(counts[m][k] for m in MODELS)]
    kinds.sort(key=lambda k: sum(counts[m][k] for m in MODELS))
    fig, ax = plt.subplots(figsize=(8.5, 0.45 * len(kinds) + 1.2))
    h = 0.26
    for j, m in enumerate(MODELS):
        ys = [i - (j - 1) * h for i in range(len(kinds))]  # M0 on top within each group, matching the legend
        vals = [counts[m][k] for k in kinds]
        ax.barh(ys, vals, height=h - 0.03, color=COLOR[m], label=NAMES[m])
        for y, v in zip(ys, vals):
            if v:
                ax.text(v + 1, y, str(v), va="center", fontsize=7.5, color=INK2)
    _style(ax)
    ax.set_yticks(range(len(kinds)), kinds, fontsize=8.5)
    ax.tick_params(axis="y", labelcolor=INK2)
    ax.yaxis.grid(False)
    ax.xaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_xlabel("failed hidden checks, all runs (one crash fails many)", color=MUTED, fontsize=9)
    ax.legend(frameon=False, fontsize=8.5, loc="lower right", labelcolor=INK2)
    ax.set_title("Why hidden checks failed", loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(out / "4_failure_taxonomy.png", dpi=200)
    plt.close(fig)
    return counts


# ---------------------------------------------------------------- main
def main(folder: Path) -> int:
    records = load(folder)
    out = folder / "analysis"
    out.mkdir(exist_ok=True)
    names = ["functional_pass", "hidden_check_rate", "false_assurance_of_accepted", "shipped_broken_per_run",
             "false_rejection_of_rejected", "benchmark_bug_recall", "own_mutation_score"]
    stats = {}
    for m in MODELS:
        rs = [r for r in records if r["model"] == m]
        stats[m] = {}
        for n in names:
            lo, hi = cluster_bootstrap(rs, n)
            v = metric_value(rs, n)
            stats[m][n] = {"value": None if v is None else round(v, 4), "ci_low": None if lo is None else round(lo, 4),
                           "ci_high": None if hi is None else round(hi, 4)}
    tests = {}
    for a, b in (("m0", "m1"), ("m0", "m2"), ("m1", "m2")):
        tests[f"{a}_vs_{b}"] = {"passes_all_hidden_checks": paired(records, a, b, lambda r: r["hidden_pass"]),
                                "shipped_broken_app": paired(records, a, b, lambda r: r["shipped_broken"])}
    counts = charts(records, stats, out / "charts")
    with open(out / "failure_taxonomy.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cause"] + MODELS)
        for k in TAXONOMY:
            w.writerow([k] + [counts[m][k] for m in MODELS])

    labels = {"functional_pass": "Passes every hidden check", "hidden_check_rate": "Hidden checks passed (mean)",
              "false_assurance_of_accepted": "Broken among shipped apps (false assurance)",
              "shipped_broken_per_run": "Runs that shipped a broken app",
              "false_rejection_of_rejected": "Correct among rejected apps (false rejection)",
              "benchmark_bug_recall": "Seeded benchmark bugs caught by own tests",
              "own_mutation_score": "Own-app mutants caught by own tests"}
    pct = lambda s: "-" if s["value"] is None else f"{s['value']:.0%} [{s['ci_low']:.0%}, {s['ci_high']:.0%}]"
    lines = ["# Demo 1 analysis", "", f"Source: `{folder.name}`, {len(records)} runs. 95% intervals: cluster bootstrap "
             f"over tasks, {N_BOOT:,} resamples.", "", "| Metric | " + " | ".join(NAMES[m] for m in MODELS) + " |",
             "|---|---|---|---|"]
    for n in names:
        lines.append(f"| {labels[n]} | " + " | ".join(pct(stats[m][n]) for m in MODELS) + " |")
    lines += ["", "## Paired comparisons (exact McNemar, same task and repeat)", "",
              "| Pair | Outcome | Pairs | Only first | Only second | p |", "|---|---|---|---|---|---|"]
    for pair, d in tests.items():
        a, b = pair.split("_vs_")
        for outcome, t in d.items():
            lines.append(f"| {a.upper()} vs {b.upper()} | {outcome.replace('_', ' ')} | {t['pairs']} | {t[f'{a}_only']} | "
                         f"{t[f'{b}_only']} | {t['p_value']} |")
    lines += ["", "## Failed hidden checks by cause", "", "| Cause | M0 | M1 | M2 |", "|---|---|---|---|"]
    for k in TAXONOMY:
        if any(counts[m][k] for m in MODELS):
            lines.append(f"| {k} | " + " | ".join(str(counts[m][k]) for m in MODELS) + " |")
    lines += ["", "Note: a failed create often makes later checks fail with a missing key, so 'wrong response shape' "
              "includes cascades.", "", "Charts: `charts/1_outcomes.png`, `2_headline_rates.png`, "
              "`3_pass_by_category.png`, `4_failure_taxonomy.png`."]
    (out / "analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "analysis.json").write_text(json.dumps({"stats": stats, "paired_tests": tests,
                                                    "failure_taxonomy": {m: dict(counts[m]) for m in MODELS}}, indent=2),
                                       encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "results/grid/demo1")))
