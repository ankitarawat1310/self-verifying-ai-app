"""Benchmark v1 task packages: PUBLIC view only.

A task is split in two folders:
  benchmarks/public/<task_id>/task.yaml     prompt + public interface (routes, roles, conventions)
  <private folder>/<task_id>/...            hidden checks, gold capabilities, state machine, reference app, mutants

This module reads only the public half. Pipelines, prompts and the RAG corpus must use this module and never
the private folder (enforced by tests/test_task_package.py). The judge and the validation scripts read the
private half through shared.benchmarks.private_loader.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from shared.benchmarks.loader import BenchmarkWorkflow, load_all_benchmarks
from shared.paths import TASK_SCHEMAS_DIR, TASKS_PUBLIC_DIR


INTERFACE_HEADER = "Public interface (implement exactly these routes with FastAPI):"


@lru_cache(maxsize=1)
def _public_validator() -> Draft202012Validator:
    schema = json.loads((TASK_SCHEMAS_DIR / "task_public.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


@dataclass(frozen=True)
class PublicTask:
    task_id: str
    title: str
    category: str
    source: str
    prompt: str
    interface: dict[str, Any]
    path: Path
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def routes(self) -> list[dict[str, Any]]:
        return list(self.interface.get("routes", []))

    @property
    def roles(self) -> list[dict[str, Any]]:
        return list(self.interface.get("roles", []))


def validate_public_task_data(data: dict[str, Any]) -> list[str]:
    """Return schema errors as readable strings (empty list = valid)."""
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in sorted(_public_validator().iter_errors(data), key=lambda e: list(e.absolute_path))]


def load_public_task(task_dir: Path | str) -> PublicTask:
    task_dir = Path(task_dir)
    if not task_dir.is_absolute() and not task_dir.exists():
        task_dir = TASKS_PUBLIC_DIR / task_dir
    data = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf-8"))
    errors = validate_public_task_data(data)
    if errors:
        raise ValueError(f"invalid public task {task_dir.name}: " + "; ".join(errors))
    if data["task_id"] != task_dir.name:
        raise ValueError(f"task_id {data['task_id']!r} does not match folder {task_dir.name!r}")
    return PublicTask(
        task_id=data["task_id"],
        title=data["title"],
        category=data["category"],
        source=data["source"],
        prompt=" ".join(data["prompt"].split()),
        interface=data["interface"],
        path=task_dir,
        raw=data,
    )


def load_all_public_tasks(directory: Path | None = None) -> list[PublicTask]:
    directory = directory or TASKS_PUBLIC_DIR
    if not directory.exists():
        return []
    return [load_public_task(p) for p in sorted(directory.iterdir()) if (p / "task.yaml").exists()]


def _field_text(name: str, spec: dict[str, Any]) -> str:
    bits = [spec["type"], "required" if spec.get("required") else "optional"]
    if spec.get("format"):
        bits.append(f"format={spec['format']}")
    for key in ("enum", "minimum", "exclusive_minimum", "maximum", "min_length", "max_length"):
        if key in spec:
            bits.append(f"{key}={spec[key]}")
    return f"{name} ({', '.join(str(b) for b in bits)})"


def render_interface_text(task: PublicTask) -> str:
    """Plain-text interface contract appended to the prompt every model receives."""
    itf = task.interface
    lines = [INTERFACE_HEADER]
    auth = itf.get("auth", {})
    if auth.get("scheme") == "headers":
        lines.append(
            f"- Caller identity comes from request headers: {auth.get('actor_header')} (user id) and "
            f"{auth.get('role_header')} (role)."
        )
    if itf.get("status_codes"):
        conv = ", ".join(f"{k.replace('_', ' ')} -> {v}" for k, v in itf["status_codes"].items())
        lines.append(f"- Status code conventions: {conv}.")
    if itf.get("clock"):
        lines.append(f"- Current time: read it from header {itf['clock']['header']} (ISO 8601) when present, else use the system clock.")
    lines.append("- Roles: " + "; ".join(f"{r['name']}: {r.get('description', '').rstrip('.')}".strip() for r in itf["roles"]) + ".")
    for svc in itf.get("mock_services", []):
        detail = f" Contract: {svc['description'].rstrip('.')}." if svc.get("description") else ""
        lines.append(f"- External service {svc['name']}: {svc['method']} {svc['url']} (the only outbound call allowed).{detail}")
    for r in itf["routes"]:
        roles = f" [roles: {', '.join(r['roles'])}]" if r.get("roles") else ""
        lines.append(f"- {r['method']} {r['path']}: {r['summary']}{roles}; success {r['success_status']}")
        if r.get("request_fields"):
            lines.append("    JSON body: " + "; ".join(_field_text(n, s) for n, s in r["request_fields"].items()))
        if r.get("query_params"):
            lines.append("    Query: " + "; ".join(_field_text(n, s) for n, s in r["query_params"].items()))
        if r.get("response_fields"):
            if r["method"].upper() == "GET" and "{" not in r["path"]:
                # every list route in the benchmark returns a bare array; say so instead of leaving it to guesswork
                lines.append("    Response: a JSON array (a bare list, not wrapped in an object) of items with fields: "
                             + ", ".join(r["response_fields"]))
            else:
                lines.append("    Response JSON fields: " + ", ".join(r["response_fields"]))
    return "\n".join(lines)


def to_benchmark_workflow(task: PublicTask, natural_language: str | None = None) -> BenchmarkWorkflow:
    """Adapt a public task to the pipelines' BenchmarkWorkflow.

    Deliberately carries NO gold data: permission_requirements is empty (each model must author its own policy),
    and there are no functional/safety properties (those live in the private hidden checks).
    """
    prompt = (natural_language or "").strip() or task.prompt
    # The console may echo back a requirement that already carries the interface block; never duplicate it.
    prompt = prompt.split(INTERFACE_HEADER)[0].strip() or task.prompt
    requirement = f"{prompt}\n\n{render_interface_text(task)}"
    raw: dict[str, Any] = {
        "workflow_id": task.task_id,
        "name": task.title,
        "category": task.category,
        "natural_language_requirement": requirement,
        "benchmark_version": "v1",
        "interface": task.interface,
        "actors": [{"id": r["name"], "name": r["name"].replace("_", " ").title()} for r in task.roles],
        "endpoints": [
            {
                "method": r["method"],
                "path": r["path"],
                "business_action": r["summary"],
                "allowed_roles": list(r.get("roles", [])),
            }
            for r in task.routes
        ],
        "business_rules": [],
        "functional_properties": [],
        "safety_properties": [],
        "permission_requirements": {},
    }
    return BenchmarkWorkflow(
        workflow_id=task.task_id,
        name=task.title,
        category=task.category,
        natural_language_requirement=requirement,
        raw=raw,
    )


def load_benchmark_catalog() -> list[BenchmarkWorkflow]:
    """v1 public tasks first, then legacy v0 YAML tasks whose ids are not shadowed by a v1 task."""
    v1 = [to_benchmark_workflow(t) for t in load_all_public_tasks()]
    seen = {b.workflow_id for b in v1}
    legacy = [b for b in load_all_benchmarks() if b.workflow_id not in seen]
    return v1 + legacy


def find_benchmark(workflow_id: str, natural_language: str | None = None) -> BenchmarkWorkflow:
    task_dir = TASKS_PUBLIC_DIR / workflow_id
    if (task_dir / "task.yaml").exists():
        return to_benchmark_workflow(load_public_task(task_dir), natural_language)
    for bench in load_all_benchmarks():
        if bench.workflow_id == workflow_id:
            return bench
    raise KeyError(f"Unknown workflow_id: {workflow_id}")
