"""Evaluate M1 retrieval on the labeled queries (model1_rag_generator/backend/rag_eval/queries.yaml).

    python scripts/evaluate_retrieval.py                 # uses nomic-embed-text in local Ollama if reachable
    python scripts/evaluate_retrieval.py --embedder hash # dependency-free fallback (lexical stand-in)

Metrics per mode (bm25, dense, hybrid, hybrid_mmr), k = 4 (what M1 puts in the prompt):
  recall@4  share of a query's relevant chunks that appear in the top 4, averaged over queries
  hit@4     share of queries with at least one relevant chunk in the top 4
  MRR@10    1 / rank of the first relevant chunk within the top 10 (0 if none), averaged
  nDCG@4    rank-weighted relevance of the top 4, normalized by the best possible order
Writes docs/demo1/retrieval_eval/<embedder>/: summary.json, per_query.csv, retrieval_modes.png.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml  # noqa: E402

from model1_rag_generator.backend.app.hybrid_rag import MODES, HashEmbedder, HybridRetriever, OllamaEmbedder  # noqa: E402
from shared.paths import SVAGA_ROOT  # noqa: E402

QUERIES = SVAGA_ROOT / "model1_rag_generator" / "backend" / "rag_eval" / "queries.yaml"
K = 4


def score(ranked: list[str], relevant: set[str]) -> dict[str, float]:
    top = ranked[:K]
    first = next((i + 1 for i, c in enumerate(ranked[:10]) if c in relevant), None)
    dcg = sum(1 / math.log2(i + 2) for i, c in enumerate(top) if c in relevant)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(K, len(relevant))))
    return {"recall@4": len(relevant & set(top)) / len(relevant), "hit@4": float(bool(relevant & set(top))),
            "MRR@10": 1 / first if first else 0.0, "nDCG@4": dcg / ideal if ideal else 0.0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--embedder", choices=["auto", "ollama", "hash"], default="auto")
    args = parser.parse_args()
    if args.embedder == "hash":
        embedder = HashEmbedder()
    else:
        try:
            embedder = OllamaEmbedder()
            embedder.embed(["ping"], kind="query")
        except Exception as error:
            if args.embedder == "ollama":
                raise SystemExit(f"Ollama embeddings unavailable: {error}")
            print(f"Ollama embeddings unavailable ({type(error).__name__}); using the hash fallback")
            embedder = HashEmbedder()
    retriever = HybridRetriever(embedder=embedder)
    queries = yaml.safe_load(QUERIES.read_text(encoding="utf-8"))["queries"]
    out = SVAGA_ROOT / "docs" / "demo1" / "retrieval_eval" / re.sub(r"[^a-z0-9]+", "_", embedder.name.lower())
    out.mkdir(parents=True, exist_ok=True)

    rows, summary = [], {"embedder": embedder.name, "queries": len(queries), "chunks": len(retriever.chunks), "k": K,
                         "modes": {}}
    for mode in MODES:
        totals = {"recall@4": 0.0, "hit@4": 0.0, "MRR@10": 0.0, "nDCG@4": 0.0}
        for q in queries:
            ranked = retriever.retrieve(q["query"], top_k=10, mode=mode, category=q.get("category")).chunk_ids
            if mode == "hybrid_mmr":  # MMR only reorders the first K; rank the rest by plain hybrid for MRR@10
                ranked = ranked[:K] + [c for c in retriever.retrieve(q["query"], top_k=10, mode="hybrid",
                                                                    category=q.get("category")).chunk_ids
                                       if c not in ranked[:K]]
            s = score(ranked, set(q["relevant"]))
            for key in totals:
                totals[key] += s[key]
            rows.append({"mode": mode, "query_id": q["id"], "source": q["source"], **{k: round(v, 3) for k, v in s.items()},
                         "top4": " ".join(ranked[:K]), "relevant": " ".join(q["relevant"])})
        summary["modes"][mode] = {k: round(v / len(queries), 3) for k, v in totals.items()}
        print(f"{mode:11} " + "  ".join(f"{k}={v:.3f}" for k, v in summary["modes"][mode].items()))

    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    with open(out / "per_query.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    _chart(summary, out / "retrieval_modes.png")
    print(f"wrote {out}")
    return 0


def _chart(summary: dict, path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    surface, ink, ink2, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    colors = {"recall@4": "#2a78d6", "MRR@10": "#eb6834", "nDCG@4": "#1baf7a"}
    default = os.getenv("SVAGA_RAG_MODE", "hybrid")
    labels = {"bm25": "Keywords (BM25)", "dense": "Meaning (embeddings)", "hybrid": "Hybrid (RRF)",
              "hybrid_mmr": "Hybrid + diversity (MMR)"}
    labels[default] += ", M1 default"
    modes = list(summary["modes"])
    fig, ax = plt.subplots(figsize=(11, 4.6), facecolor=surface)
    height = 0.24
    for j, metric in enumerate(colors):
        ys = [i + (j - 1) * height for i in range(len(modes))]
        vals = [summary["modes"][m][metric] for m in modes]
        ax.barh(ys, vals, height=height, color=colors[metric], edgecolor=surface, linewidth=2, label=metric)
        for y, v in zip(ys, vals):
            ax.text(v + 0.01, y, f"{v:.2f}", va="center", fontsize=9, color=ink2)
    ax.set_yticks(range(len(modes)), [labels[m] for m in modes])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.08)
    ax.set_facecolor(surface)
    ax.set_title(f"M1 retrieval on {summary['queries']} labeled queries ({summary['embedder']})", loc="left",
                 fontsize=15, color=ink, pad=34, fontweight="bold")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, frameon=False, fontsize=10, labelcolor=ink2)
    ax.set_xlabel("score (1.0 = perfect)", color=ink2)
    ax.tick_params(colors=ink2, length=0)
    ax.grid(axis="x", color=grid, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(grid)
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=surface)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
