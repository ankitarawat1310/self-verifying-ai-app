from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from svaga_platform.app.workflow_run import run_workflow

router = APIRouter()


class GenerateRequest(BaseModel):
    prompt: str


@router.post("/api/v1/generate-model1")
def generate_model1(req: GenerateRequest):
    payload = run_workflow(
        pipeline="m1",
        natural_language=req.prompt,
        workflow_id=None,
    )
    artifacts = payload.get("artifacts") or {}
    verification = payload.get("verification") or {}
    pytest_block = next(
        (v for v in verification.get("verifiers", []) if v.get("name") == "pytest_sandbox"),
        {},
    )
    details = pytest_block.get("details") or {}
    return {
        "run_id": payload.get("run_id"),
        "app_code": artifacts.get("app.py", ""),
        "test_code": artifacts.get("test_app.py", ""),
        "workflow_spec": artifacts.get("workflow_spec.json", ""),
        "policy": artifacts.get("policy.json", ""),
        "retrieved_context": (payload.get("provenance") or {}).get("retrieved_context", ""),
        "verification_results": details,
        "verification": verification,
        "decision": payload.get("decision"),
        "release_gate": payload.get("release_gate"),
        "verified": payload.get("decision") == "ACCEPT",
        "provenance": payload.get("provenance"),
    }
