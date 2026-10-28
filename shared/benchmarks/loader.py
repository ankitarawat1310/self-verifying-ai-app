from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from shared.paths import BENCHMARKS_DIR


@dataclass
class BenchmarkWorkflow:
    workflow_id: str
    name: str
    category: str
    natural_language_requirement: str
    raw: dict[str, Any] = field(repr=False)

    @property
    def functional_properties(self) -> list[dict[str, Any]]:
        return self.raw.get("functional_properties", [])

    @property
    def safety_properties(self) -> list[dict[str, Any]]:
        return self.raw.get("safety_properties", [])

    @property
    def permission_requirements(self) -> dict[str, Any]:
        return self.raw.get("permission_requirements", {})


def _schema_path() -> Path:
    return BENCHMARKS_DIR.parent / "schema" / "workflow_benchmark.schema.json"


def load_benchmark(path: Path) -> BenchmarkWorkflow:
    import json

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    sp = _schema_path()
    schema = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else None
    if schema:
        Draft202012Validator(schema).validate(data)
    return BenchmarkWorkflow(
        workflow_id=data["workflow_id"],
        name=data.get("name", data["workflow_id"]),
        category=data.get("category", "general"),
        natural_language_requirement=data["natural_language_requirement"],
        raw=data,
    )


def load_all_benchmarks(directory: Path | None = None) -> list[BenchmarkWorkflow]:
    directory = directory or BENCHMARKS_DIR
    items = sorted(directory.glob("*.yaml"))
    return [load_benchmark(p) for p in items]
