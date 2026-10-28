"""Benchmark v1 PRIVATE task data: hidden checks, gold capabilities, state machine, reference app, mutants.

Only the judge, the benchmark validation scripts and tests may import this module. Anything that builds a prompt,
a spec, a policy or a RAG corpus must not (enforced by tests/test_task_package.py).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from shared.paths import TASK_SCHEMAS_DIR, TASKS_PRIVATE_DIR


@lru_cache(maxsize=1)
def _private_validator() -> Draft202012Validator:
    schema = json.loads((TASK_SCHEMAS_DIR / "task_private.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


@dataclass(frozen=True)
class PrivateTask:
    task_id: str
    canary: str
    split: str
    gold_capabilities: list[dict[str, str]]
    hidden_checks: list[dict[str, str]]
    state_machine: dict[str, Any] | None
    security_mutants: list[dict[str, Any]]
    path: Path
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def checks_file(self) -> Path:
        return self.path / "checks" / "test_hidden.py"

    @property
    def reference_app(self) -> Path:
        return self.path / "reference" / "app.py"

    @property
    def mutants_dir(self) -> Path:
        return self.path / "mutants"


def validate_private_task_data(data: dict[str, Any]) -> list[str]:
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in sorted(_private_validator().iter_errors(data), key=lambda e: list(e.absolute_path))]


def load_private_task(task_id: str, directory: Path | None = None) -> PrivateTask:
    task_dir = (directory or TASKS_PRIVATE_DIR) / task_id
    data = yaml.safe_load((task_dir / "private.yaml").read_text(encoding="utf-8"))
    errors = validate_private_task_data(data)
    if errors:
        raise ValueError(f"invalid private task {task_id}: " + "; ".join(errors))
    if data["task_id"] != task_id:
        raise ValueError(f"task_id {data['task_id']!r} does not match folder {task_id!r}")
    return PrivateTask(
        task_id=task_id,
        canary=data["canary"],
        split=data["split"],
        gold_capabilities=list(data["gold_capabilities"]),
        hidden_checks=list(data["hidden_checks"]),
        state_machine=data.get("state_machine"),
        security_mutants=list(data.get("security_mutants", [])),
        path=task_dir,
        raw=data,
    )


def load_all_private_tasks(directory: Path | None = None) -> list[PrivateTask]:
    directory = directory or TASKS_PRIVATE_DIR
    if not directory.exists():
        return []
    return [load_private_task(p.name, directory) for p in sorted(directory.iterdir()) if (p / "private.yaml").exists()]


def all_canaries() -> dict[str, str]:
    return {t.task_id: t.canary for t in load_all_private_tasks()}
