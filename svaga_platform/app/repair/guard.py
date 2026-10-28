"""Prevent repair agent from weakening spec or policy."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _hash(obj: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def assert_immutable_artifacts(
    *,
    before_spec: dict[str, Any],
    after_spec: dict[str, Any],
    before_policy: dict[str, Any],
    after_policy: dict[str, Any],
) -> None:
    if _hash(before_spec) != _hash(after_spec):
        raise ValueError("Repair attempted to modify frozen workflow_spec")
    if _hash(before_policy) != _hash(after_policy):
        raise ValueError("Repair attempted to modify frozen policy")
