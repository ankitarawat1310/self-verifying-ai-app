from __future__ import annotations

from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from shared.benchmarks.task_package import find_benchmark, load_benchmark_catalog
from shared.budget.tracker import BudgetProfile, BudgetTracker
from shared.paths import BENCHMARKS_DIR, RESULTS_DIR

from svaga_platform.app.experiments.runner import run_experiment
from svaga_platform.app.pipelines.registry import get_pipeline
from svaga_platform.app.preview_manager import start_preview, stop_preview
from svaga_platform.app.run_store import build_zip, load_run
from svaga_platform.app.spec_from_nl import llm_provider_label
from svaga_platform.app.workflow_run import run_workflow

app = FastAPI(title="SVAGA 3.0 Platform", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5303",
        "http://127.0.0.1:5303",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    workflow_id: str
    pipeline: str = "m1"
    budget_profile: dict[str, Any] | None = None


class WorkflowRunRequest(BaseModel):
    pipeline: str = "m1"
    natural_language: str = Field(min_length=1)
    workflow_id: str | None = None
    budget_profile: dict[str, Any] | None = None


class ExperimentRequest(BaseModel):
    workflow_ids: list[str] = Field(min_length=1)
    pipelines: list[str] = Field(default_factory=lambda: ["m1", "m2", "m3", "m4"])
    budget_profile: dict[str, Any] | None = None


@app.get("/api/v1/health")
def health():
    from shared.llm.provider import describe_llm_provider

    return {
        "status": "ok",
        "platform": "svaga_3.0",
        "version": "0.2.0",
        "llm": describe_llm_provider(),
    }


@app.get("/api/v1/config")
def platform_config():
    return {
        "platform": "svaga_3.0",
        "llm": llm_provider_label(),
        "console_hint": "http://localhost:5303",
        "api_hint": "http://127.0.0.1:8003",
    }


@app.get("/api/v1/benchmarks")
def list_benchmarks():
    return [
        {
            "workflow_id": b.workflow_id,
            "name": b.name,
            "category": b.category,
            "natural_language_requirement": b.natural_language_requirement,
            "benchmark_version": b.raw.get("benchmark_version", "v0"),
        }
        for b in load_benchmark_catalog()
    ]


@app.post("/api/v1/workflows/run")
def workflows_run(payload: WorkflowRunRequest):
    profile = BudgetProfile(**payload.budget_profile) if payload.budget_profile else BudgetProfile()
    try:
        return run_workflow(
            pipeline=payload.pipeline,
            natural_language=payload.natural_language,
            workflow_id=payload.workflow_id,
            budget=BudgetTracker(profile=profile),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/runs/{run_id}")
def get_run(run_id: str):
    try:
        return load_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc


@app.get("/api/v1/runs/{run_id}/download")
def download_run(run_id: str):
    try:
        data = build_zip(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="svaga_{run_id}.zip"'},
    )


@app.post("/api/v1/runs/{run_id}/preview/start")
def preview_start(run_id: str):
    try:
        return start_preview(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/v1/runs/{run_id}/preview/stop")
def preview_stop(run_id: str):
    return stop_preview(run_id)


@app.post("/api/v1/run")
def run_pipeline(payload: RunRequest):
    try:
        bench = find_benchmark(payload.workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="workflow not found") from exc
    profile = BudgetProfile(**payload.budget_profile) if payload.budget_profile else BudgetProfile()
    return run_workflow(
        pipeline=payload.pipeline,
        natural_language=bench.natural_language_requirement,
        workflow_id=payload.workflow_id,
        budget=BudgetTracker(profile=profile),
    )


@app.post("/api/v1/experiments")
def start_experiment(payload: ExperimentRequest):
    profile = BudgetProfile(**payload.budget_profile) if payload.budget_profile else BudgetProfile()
    return run_experiment(payload.workflow_ids, payload.pipelines, budget_profile=profile)


@app.get("/api/v1/experiments/results")
def list_experiment_results():
    if not RESULTS_DIR.exists():
        return []
    rows = []
    for d in sorted(RESULTS_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        summary = d / "summary.json"
        metrics = d / "metrics.json"
        if summary.exists() or metrics.exists():
            rows.append({"experiment_id": d.name, "path": str(d)})
    return rows[:50]


from model1_rag_generator.backend.app.main import router as model1_router  # noqa: E402

app.include_router(model1_router)

from svaga_platform.app.results_api import router as results_router  # noqa: E402

app.include_router(results_router)
