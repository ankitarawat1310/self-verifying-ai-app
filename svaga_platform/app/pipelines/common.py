from __future__ import annotations

from shared.benchmarks.loader import BenchmarkWorkflow
from shared.policy.checker import PolicyDocument
from shared.schemas.workflow_spec import ActorSpec, EndpointSpec, WorkflowSpecDocument

from svaga_platform.app.artifacts import PipelineArtifacts
from svaga_platform.app.release_gate import evaluate_release_gate
from svaga_platform.app.verification.orchestrator import run_full_verification


def default_policy_from_benchmark(benchmark: BenchmarkWorkflow) -> PolicyDocument:
    gold = benchmark.permission_requirements or {}
    forbidden = gold.get("forbidden_imports", ["subprocess", "socket", "os.system"])
    allowed = gold.get("allowed_imports", ["fastapi", "pydantic", "typing"])
    return PolicyDocument(allowed_imports=allowed, forbidden_imports=forbidden)


def minimal_spec_from_benchmark(benchmark: BenchmarkWorkflow) -> WorkflowSpecDocument:
    actors_raw = benchmark.raw.get("actors") or [{"id": "user", "name": "User"}]
    actors = [ActorSpec(**a) if isinstance(a, dict) else ActorSpec(id="user", name="User") for a in actors_raw]
    endpoints_raw = benchmark.raw.get("endpoints") or [
        {"method": "GET", "path": "/health", "business_action": "health"}
    ]
    endpoints = [EndpointSpec(**e) for e in endpoints_raw]
    rules = benchmark.raw.get("business_rules") or []
    br = [{"id": r.get("id", r.get("name", f"rule_{i}")), "description": r.get("description", ""), "actors": r.get("actors", [])} for i, r in enumerate(rules)]
    from shared.schemas.workflow_spec import BusinessRuleSpec

    return WorkflowSpecDocument(
        workflow_id=benchmark.workflow_id,
        application_name=benchmark.name,
        description=benchmark.natural_language_requirement,
        actors=actors,
        entities=[],
        business_rules=[BusinessRuleSpec(**r) for r in br] if br else [],
        endpoints=endpoints,
        invariants=[p.get("description", "") for p in benchmark.safety_properties],
    )


def finalize_pipeline_result(
    pipeline: str,
    benchmark: BenchmarkWorkflow,
    artifacts: PipelineArtifacts,
    budget,
    *,
    frozen_spec_hash: str | None = None,
    profile: str = "pragmatic",
):
    from svaga_platform.app.pipelines.base import PipelineResult

    verification = run_full_verification(artifacts, benchmark, budget, profile=profile)
    policy_passed = all(v["passed"] for v in verification.verifiers if v["name"] == "policy_static")
    gate = evaluate_release_gate(
        verification,
        spec_hash=artifacts.spec_hash,
        frozen_spec_hash=frozen_spec_hash,
        policy_passed=policy_passed,
    )
    return PipelineResult(
        pipeline=pipeline,
        workflow_id=benchmark.workflow_id,
        artifacts=artifacts,
        verification=verification.to_dict(),
        decision=gate.decision,
        budget=budget.to_dict(),
        counterexamples=verification.counterexamples,
        metadata={"gate_reasons": gate.reasons},
    )
