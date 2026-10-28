"""M2: spec-first synthesis.

Order of work (the point of M2 is that the spec exists and is checked before any code):
1. The LLM writes a BehaviorSpec from the requirement and the interface skeleton (entities, state machine,
   per-transition roles, rules such as "requester cannot approve own request").
2. The spec is checked: structural checks against the interface plus a bounded model checker over the state
   machine. Problems go back to the LLM once; if the spec still fails, M2 falls back to the interface-only spec.
3. The spec is frozen: its SHA-256 hash is recorded before code is generated.
4. The LLM writes app_code only, from the frozen spec (plus the same retrieved context M1 uses).
5. Tests are generated from the frozen spec by code, not by the LLM.
6. The same verifiers and release gate as M1 decide ACCEPT or REJECT. The gate also checks the spec hash did not
   change after code generation.
"""
from __future__ import annotations

import json
import os

from shared.benchmarks.loader import BenchmarkWorkflow
from shared.budget.tracker import BudgetTracker
from shared.llm.provider import get_llm_provider
from shared.policy.checker import PolicyDocument

from svaga_platform.app.artifacts import PipelineArtifacts
from svaga_platform.app.pipelines.base import Pipeline, PipelineResult
from svaga_platform.app.pipelines.common import finalize_pipeline_result, minimal_spec_from_benchmark
from svaga_platform.app.spec_first.author import author_spec, synthesize_app
from svaga_platform.app.spec_first.spec_tests import generate_spec_tests
from svaga_platform.app.verification.orchestrator import VerificationReport

NO_CONTEXT = "(none: retrieval turned off for M2)"


def interface_of(benchmark: BenchmarkWorkflow) -> dict:
    """Public interface for v1 tasks; for legacy tasks, a minimal one built from their endpoint list."""
    iface = benchmark.raw.get("interface")
    if iface:
        return iface
    roles = sorted({r for e in benchmark.raw.get("endpoints") or [] for r in e.get("allowed_roles", [])})
    return {
        "auth": {"scheme": "none"},
        "status_codes": {},
        "roles": [{"name": r} for r in roles],
        "routes": [
            {"method": e.get("method", "GET"), "path": e.get("path", "/health"), "summary": e.get("business_action", ""),
             "roles": [], "success_status": 200}
            for e in (benchmark.raw.get("endpoints") or [{"method": "GET", "path": "/health"}])
        ],
    }


class M2SpecFirstPipeline(Pipeline):
    name = "m2"

    def run(self, benchmark: BenchmarkWorkflow, *, budget: BudgetTracker, model: str | None = None) -> PipelineResult:
        llm = get_llm_provider()
        requirement = benchmark.natural_language_requirement
        interface = interface_of(benchmark)

        # 1-3: author, check, freeze
        spec, spec_meta = author_spec(llm, benchmark.workflow_id, requirement, interface, budget=budget)
        frozen_behavior_hash = spec.spec_hash()
        tests_src, tests_summary = generate_spec_tests(spec, interface)

        # 4: code from the frozen spec
        retrieval = None
        context = NO_CONTEXT
        if os.getenv("SVAGA_M2_RETRIEVAL", "1").lower() not in ("0", "false", "no"):
            from model1_rag_generator.backend.app.retriever import retrieve_with_provenance

            context, retrieval = retrieve_with_provenance(requirement, category=benchmark.category)
        generated = synthesize_app(llm, requirement, spec, context, budget=budget)

        policy = PolicyDocument(allowed_imports=spec.policy.allowed_imports, forbidden_imports=spec.policy.forbidden_imports)
        spec_files = {
            "behavior_spec.json": json.dumps(spec.model_dump(mode="json"), indent=2),
            "behavior_spec.sha256": frozen_behavior_hash + "\n",
        }
        artifacts = PipelineArtifacts(
            app_code=generated["app_code"],
            test_code=tests_src,
            workflow_spec=minimal_spec_from_benchmark(benchmark),
            policy=policy,
            metadata={"retrieved_context": context, "retrieval": retrieval},
            extra_files=spec_files,
        )
        metadata = {
            "behavior_spec_hash": frozen_behavior_hash,
            "spec_source": spec_meta["source"],
            "spec_attempts": spec_meta["attempts"],
            "spec_checks": spec_meta["history"],
            "spec_tests": tests_summary,
            "retrieval": retrieval,
            "retrieved_context": context,
        }
        if generated.get("malformed_reason"):
            artifacts.app_code = ""
            reason = generated["malformed_reason"]
            report = VerificationReport(
                passed=False,
                verifiers=[{"name": "generation_output", "passed": False, "details": {"error": reason}, "wall_seconds": 0.0}],
                counterexamples=[{"property_id": "generation_output", "message": reason, "spec_rule_id": "generation_output"}],
            )
            return PipelineResult(self.name, benchmark.workflow_id, artifacts, report.to_dict(), "REJECT",
                                  budget.to_dict(), report.counterexamples, {"gate_reasons": [reason], **metadata})

        # 5-6: verify; the behavior spec must be unchanged since it was frozen
        result = finalize_pipeline_result(self.name, benchmark, artifacts, budget, frozen_spec_hash=artifacts.spec_hash)
        if spec.spec_hash() != frozen_behavior_hash:  # pragma: no cover - defensive: nothing should mutate it
            result.decision = "REJECT"
            result.metadata.setdefault("gate_reasons", []).append("behavior spec changed after it was frozen")
        result.metadata = {**result.metadata, **metadata}
        return result
