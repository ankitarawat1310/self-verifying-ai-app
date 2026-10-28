from __future__ import annotations

from typing import Any

from shared.benchmarks.loader import BenchmarkWorkflow
from shared.budget.tracker import BudgetTracker
from shared.llm.provider import LLMProvider
from shared.policy.checker import PolicyDocument
from shared.schemas.validator import validate_workflow_spec
from shared.schemas.workflow_spec import WorkflowSpecDocument

from svaga_platform.app.pipelines.common import default_policy_from_benchmark, minimal_spec_from_benchmark


def generate_spec_from_nl(
    llm: LLMProvider,
    benchmark: BenchmarkWorkflow,
    *,
    budget: BudgetTracker | None = None,
) -> WorkflowSpecDocument:
    prompt = (
        "WorkflowSpec author: emit JSON WorkflowSpec for the requirement. "
        f"Requirement: {benchmark.natural_language_requirement}"
    )
    try:
        spec_json = llm.complete_json("WorkflowSpec author", prompt, budget=budget)
        ok, _errors = validate_workflow_spec(spec_json)
        if ok:
            return WorkflowSpecDocument.model_validate(spec_json)
    except (ValueError, TypeError, AttributeError):
        # non-JSON / wrong-shape model output: same fallback as an invalid spec
        pass
    return minimal_spec_from_benchmark(benchmark)


def generate_policy_from_nl(
    llm: LLMProvider,
    benchmark: BenchmarkWorkflow,
    *,
    budget: BudgetTracker | None = None,
) -> PolicyDocument:
    fallback = default_policy_from_benchmark(benchmark)
    prompt = (
        "Least-privilege policy JSON with keys: allowed_imports, forbidden_imports, "
        "allowed_file_roots, max_upload_bytes (optional). "
        f"Requirement: {benchmark.natural_language_requirement}"
    )
    try:
        raw = llm.complete_json("Policy author", prompt, budget=budget)
        if isinstance(raw, dict) and "policy" in raw:
            raw = raw["policy"]
        return PolicyDocument.model_validate(raw)
    except Exception:
        return fallback


def llm_provider_label() -> dict[str, Any]:
    from shared.llm.provider import describe_llm_provider

    return describe_llm_provider()


def resolve_workflow_spec(
    llm: LLMProvider,
    benchmark: BenchmarkWorkflow,
    *,
    budget: BudgetTracker | None = None,
) -> WorkflowSpecDocument:
    """Use benchmark YAML as source of truth; LLM spec only for ad-hoc runs."""
    if benchmark.workflow_id.startswith("adhoc_"):
        return generate_spec_from_nl(llm, benchmark, budget=budget)
    return minimal_spec_from_benchmark(benchmark)
