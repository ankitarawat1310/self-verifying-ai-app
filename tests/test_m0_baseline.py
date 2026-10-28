"""M0 plain-prompt baseline: one call, no retrieval, ships when its own tests pass."""
from __future__ import annotations

from shared.budget.tracker import BudgetTracker
from shared.llm.provider import ScriptedLLMProvider
from svaga_platform.app.pipelines.registry import PIPELINES, get_pipeline


def test_m0_is_registered():
    assert "m0" in PIPELINES and get_pipeline("m0").name == "m0"


def test_m0_uses_one_call_no_context_and_only_its_own_tests(monkeypatch):
    import svaga_platform.app.pipelines.m0_plain as m0
    from shared.benchmarks.task_package import find_benchmark

    prompts = []

    class Recorder(ScriptedLLMProvider):
        def complete_json(self, system, user, *, budget=None, **kwargs):
            prompts.append(user)
            return super().complete_json(system, user, budget=budget)

    monkeypatch.setattr(m0, "get_llm_provider", lambda: Recorder())
    budget = BudgetTracker()
    result = get_pipeline("m0").run(find_benchmark("approval_leave_request"), budget=budget)
    assert budget.llm_calls == 1 and len(prompts) == 1
    assert "no retrieval" in prompts[0]
    assert [v["name"] for v in result.verification["verifiers"]] == ["own_tests"]
    assert result.decision == ("ACCEPT" if result.verification["passed"] else "REJECT")


def test_m1_records_which_chunks_it_retrieved(monkeypatch):
    monkeypatch.setenv("SVAGA_SCRIPTED_LLM", "1")
    from shared.benchmarks.task_package import find_benchmark

    result = get_pipeline("m1").run(find_benchmark("approval_leave_request"), budget=BudgetTracker())
    retrieval = result.metadata["retrieval"]
    assert retrieval["chunk_ids"] and retrieval["embedder"] and retrieval["mode"] == "hybrid"
