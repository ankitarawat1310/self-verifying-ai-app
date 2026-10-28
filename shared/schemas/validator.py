"""JSON Schema validation helpers."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=8)
def _load_schema(name: str) -> dict[str, Any]:
    path = SCHEMA_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def validate_workflow_spec(spec: dict[str, Any]) -> tuple[bool, list[str]]:
    schema = _load_schema("workflow_spec.schema.json")
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted({e.message for e in validator.iter_errors(spec)})
    return len(errors) == 0, errors


def validate_verification_report(report: dict[str, Any]) -> tuple[bool, list[str]]:
    schema = _load_schema("verification_report.schema.json")
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted({e.message for e in validator.iter_errors(report)})
    return len(errors) == 0, errors
