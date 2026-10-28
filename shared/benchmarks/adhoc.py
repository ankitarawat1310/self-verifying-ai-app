from __future__ import annotations

import hashlib
from typing import Any

from shared.benchmarks.loader import BenchmarkWorkflow


def adhoc_benchmark_from_nl(natural_language: str) -> BenchmarkWorkflow:
    """Synthetic benchmark for free-form NL runs (no YAML file)."""
    slug = hashlib.sha256(natural_language.encode()).hexdigest()[:12]
    workflow_id = f"adhoc_{slug}"
    raw: dict[str, Any] = {
        "workflow_id": workflow_id,
        "name": "Ad hoc workflow",
        "category": "adhoc",
        "natural_language_requirement": natural_language,
        "actors": [{"id": "user", "name": "User"}],
        "business_rules": [],
        "functional_properties": [],
        "safety_properties": [],
        "permission_requirements": {
            "forbidden_imports": ["subprocess", "socket", "os.system", "requests"],
            "allowed_imports": ["fastapi", "pydantic", "typing", "httpx"],
        },
    }
    return BenchmarkWorkflow(
        workflow_id=workflow_id,
        name=raw["name"],
        category=raw["category"],
        natural_language_requirement=natural_language,
        raw=raw,
    )
