from __future__ import annotations

from typing import Any

from svaga_platform.app.pipelines.base import PipelineResult


def build_counterexample(result: PipelineResult) -> dict[str, Any]:
    if result.counterexamples:
        return result.counterexamples[0]
    for verifier in result.verification.get("verifiers", []):
        if not verifier.get("passed"):
            return {
                "property_id": verifier.get("name"),
                "message": verifier.get("details"),
                "stdout": "",
                "stderr": "",
            }
    return {"property_id": "unknown", "message": "verification failed"}


def apply_repair_patch(original_app: str, patch: str) -> str:
    if not patch.strip():
        return original_app
    if "def " in patch or "class " in patch or "app = " in patch:
        return patch
    return original_app + "\n" + patch
