"""Read-only API over results/grid/<name>/ for the console's Results and Compare pages.

Serves saved records, summaries, the Day 10 analysis and charts, and per-run files. It never runs a model or the
judge. Grid names and file names are checked against a strict pattern, so no path outside results/grid is readable.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from shared.paths import RESULTS_DIR

router = APIRouter(prefix="/api/v1/grid", tags=["results"])
GRID_DIR = RESULTS_DIR / "grid"
SAFE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
MODELS = ("m0", "m1", "m2", "m3", "m4")
RUN_FILES = ("app.py", "test_app.py", "behavior_spec.json", "workflow_spec.json", "policy.json")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _grid(name: str) -> Path:
    if not SAFE.match(name) or name.startswith("."):
        raise HTTPException(400, "bad grid name")
    folder = GRID_DIR / name
    if not folder.is_dir():
        raise HTTPException(404, "grid not found")
    return folder


def _slim(rec: dict[str, Any]) -> dict[str, Any]:
    keys = ("model", "task", "category", "repeat", "decision", "hidden_passed", "hidden_total", "hidden_pass",
            "false_assurance", "false_rejection", "violation_recall", "own_mutation_score", "failed_verifiers",
            "wall_seconds", "error")
    return {k: rec.get(k) for k in keys}


@router.get("")
def list_grids() -> list[dict[str, Any]]:
    if not GRID_DIR.exists():
        return []
    out = []
    for d in sorted(GRID_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if d.is_dir() and SAFE.match(d.name):
            cfg = _read_json(d / "config.json") or {}
            out.append({"name": d.name, "split": cfg.get("split"), "models": cfg.get("models"),
                        "tasks": len(cfg.get("tasks") or []), "repeats": cfg.get("repeats"),
                        "llm": cfg.get("llm"), "runs": sum(1 for _ in d.glob("*/*/r*/record.json")),
                        "has_analysis": (d / "analysis" / "analysis.json").exists()})
    return out


@router.get("/{name}")
def grid_summary(name: str) -> dict[str, Any]:
    folder = _grid(name)
    records = [_slim(json.loads(p.read_text(encoding="utf-8"))) for p in sorted(folder.glob("*/*/r*/record.json"))]
    charts = sorted(p.name for p in (folder / "analysis" / "charts").glob("*.png")) if (folder / "analysis").exists() else []
    return {"name": name, "config": _read_json(folder / "config.json"), "summary": _read_json(folder / "summary.json"),
            "analysis": _read_json(folder / "analysis" / "analysis.json"), "charts": charts, "runs": records}


@router.get("/{name}/charts/{file}")
def grid_chart(name: str, file: str):
    folder = _grid(name)
    if not SAFE.match(file) or not file.endswith(".png"):
        raise HTTPException(400, "bad file name")
    path = folder / "analysis" / "charts" / file
    if not path.exists():
        raise HTTPException(404, "chart not found")
    return FileResponse(path, media_type="image/png")


@router.get("/{name}/compare")
def compare_cell(name: str, task: str, repeat: int = 1) -> dict[str, Any]:
    """Every model's run for one task and repeat, side by side."""
    folder = _grid(name)
    if not SAFE.match(task):
        raise HTTPException(400, "bad task id")
    models = {}
    for m in MODELS:
        run = folder / m / task / f"r{repeat}"
        rec = _read_json(run / "record.json")
        if rec is None:
            continue
        judge = _read_json(run / "judge.json") or {}
        meta = _read_json(run / "metadata.json") or {}
        models[m] = {
            **_slim(rec),
            "failed_checks": [{"id": c["id"], "kind": c["kind"], "detail": (c.get("detail") or "")[:300]}
                              for c in judge.get("checks", []) if not c.get("passed")],
            "spec_source": meta.get("spec_source"), "spec_tests": meta.get("spec_tests"),
            "gate_reasons": meta.get("gate_reasons"),
            "files": {f: (run / f).read_text(encoding="utf-8") for f in RUN_FILES if (run / f).exists()},
        }
    if not models:
        raise HTTPException(404, "no runs for that task and repeat")
    return {"task": task, "repeat": repeat, "models": models}
