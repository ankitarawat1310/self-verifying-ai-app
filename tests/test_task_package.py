"""Benchmark v1 task packages: schema validity and the public/private separation.

The separation is what makes the false-assurance metric meaningful: if hidden checks, gold capabilities or the
reference app ever reached a model, the model could be graded on answers it was shown.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from shared.benchmarks.private_loader import load_all_private_tasks
from shared.benchmarks.task_package import (
    INTERFACE_HEADER,
    find_benchmark,
    render_interface_text,
    load_all_public_tasks,
    load_benchmark_catalog,
    to_benchmark_workflow,
    validate_public_task_data,
)
from shared.llm.provider import ScriptedLLMProvider
from shared.paths import SVAGA_ROOT

PUBLIC = load_all_public_tasks()
PRIVATE = {t.task_id: t for t in load_all_private_tasks()}


def test_at_least_one_v1_task_exists():
    assert PUBLIC, "benchmarks/public should contain v1 tasks"


def test_every_public_task_has_matching_private_data():
    assert {t.task_id for t in PUBLIC} == set(PRIVATE)


def test_canaries_are_unique():
    canaries = [t.canary for t in PRIVATE.values()]
    assert len(canaries) == len(set(canaries))


def test_schema_rejects_unknown_keys_and_bad_category():
    data = dict(PUBLIC[0].raw)
    assert validate_public_task_data(data) == []
    assert validate_public_task_data({**data, "gold_capabilities": []})
    assert validate_public_task_data({**data, "category": "misc"})


def test_hidden_check_ids_are_unique_per_task():
    for task in PRIVATE.values():
        ids = [c["id"] for c in task.hidden_checks]
        assert len(ids) == len(set(ids)), task.task_id


def test_state_machine_is_consistent():
    for task in PRIVATE.values():
        sm = task.state_machine
        if not sm:
            continue
        states = set(sm["states"])
        assert sm["initial"] in states
        assert set(sm["terminal"]) <= states
        for tr in sm["transitions"]:
            assert tr["from"] in states and tr["to"] in states
            assert tr["from"] not in sm["terminal"], "terminal states must have no outgoing transitions"


def test_adapter_carries_no_private_data():
    for task in PUBLIC:
        bench = to_benchmark_workflow(task)
        blob = json.dumps(bench.raw) + bench.natural_language_requirement
        assert PRIVATE[task.task_id].canary not in blob
        assert bench.raw["permission_requirements"] == {}
        assert bench.functional_properties == [] and bench.safety_properties == []
        for check in PRIVATE[task.task_id].hidden_checks:
            assert check["id"] not in blob
        assert [e["path"] for e in bench.raw["endpoints"]] == [r["path"] for r in task.routes]


def test_interface_block_is_appended_once():
    task = PUBLIC[0]
    first = find_benchmark(task.task_id)
    echoed = find_benchmark(task.task_id, first.natural_language_requirement)
    assert echoed.natural_language_requirement.count(INTERFACE_HEADER) == 1
    custom = find_benchmark(task.task_id, "My own wording of the request.")
    assert custom.natural_language_requirement.startswith("My own wording")
    assert INTERFACE_HEADER in custom.natural_language_requirement


def test_catalog_lists_v1_before_legacy():
    catalog = load_benchmark_catalog()
    versions = [b.raw.get("benchmark_version", "v0") for b in catalog]
    assert versions[: len(PUBLIC)] == ["v1"] * len(PUBLIC)


# --- the model-facing code must never touch private data -------------------------------------------------------

MODEL_FACING = [
    "svaga_platform/app/pipelines",
    "svaga_platform/app/spec_from_nl.py",
    "svaga_platform/app/workflow_run.py",
    "svaga_platform/app/verification",
    "model1_rag_generator",
    "svaga_platform/app/pipelines/m0_plain.py",
    "svaga_platform/app/spec_first",
    "shared/llm",
    "shared/generation",
    "shared/benchmarks/task_package.py",
]


def _python_files(rel: str) -> list[Path]:
    path = SVAGA_ROOT / rel
    if path.is_file():
        return [path]
    return [p for p in path.rglob("*.py") if "node_modules" not in p.parts]


def test_model_facing_code_never_imports_private_loader():
    offenders = []
    for rel in MODEL_FACING:
        for py in _python_files(rel):
            source = py.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                if any("private_loader" in n for n in names):
                    offenders.append(str(py.relative_to(SVAGA_ROOT)))
            if "TASKS_PRIVATE_DIR" in source or "benchmarks/private" in source.replace("\\\\", "/"):
                offenders.append(str(py.relative_to(SVAGA_ROOT)))
    assert offenders == []


class RecordingProvider(ScriptedLLMProvider):
    def __init__(self):
        self.prompts: list[str] = []

    def complete_json(self, system, user, *, budget=None, **kwargs):
        self.prompts.append(system + "\n" + user)
        return super().complete_json(system, user, budget=budget)


@pytest.mark.parametrize("pipeline_name", ["m0", "m1", "m2", "m3", "m4"])
def test_no_private_data_reaches_prompts_or_artifacts(monkeypatch, pipeline_name):
    """Canary test: every private.yaml holds a unique marker; it must never appear in anything a model sees or makes."""
    monkeypatch.setenv("SVAGA_SCRIPTED_LLM", "1")
    import svaga_platform.app.pipelines.m0_plain as m0
    import svaga_platform.app.pipelines.m1_rag as m1
    import svaga_platform.app.pipelines.m2_spec_first as m2
    import svaga_platform.app.pipelines.m3_invariants as m3
    import svaga_platform.app.pipelines.m4_cegr as m4
    from shared.budget.tracker import BudgetProfile, BudgetTracker
    from svaga_platform.app.pipelines.registry import get_pipeline

    recorder = RecordingProvider()
    for module in (m0, m1, m2, m3, m4):
        monkeypatch.setattr(module, "get_llm_provider", lambda: recorder)

    task = PUBLIC[0]
    canary = PRIVATE[task.task_id].canary
    bench = find_benchmark(task.task_id)
    budget = BudgetTracker(profile=BudgetProfile(max_repair_rounds=1, max_llm_calls=20))
    result = get_pipeline(pipeline_name).run(bench, budget=budget)

    assert recorder.prompts, "pipeline should have called the LLM"
    for prompt in recorder.prompts:
        assert canary not in prompt
    for content in result.artifacts.to_files().values():
        assert canary not in content
    assert canary not in json.dumps(result.metadata, default=str)


def test_every_mock_service_contract_reaches_the_model():
    """The request/reply contract of an external service lives in `description`; a model that never sees it
    has to guess the outbound keys (webhook_dispatcher sent `id` instead of `event_id`)."""
    tasks = [t for t in load_all_public_tasks() if t.raw["interface"].get("mock_services")]
    assert len(tasks) >= 5
    for task in tasks:
        rendered = render_interface_text(task)
        for svc in task.raw["interface"]["mock_services"]:
            assert svc["description"].rstrip(".") in rendered, (task.task_id, svc["name"])
            assert svc["url"] in rendered
            # and it is part of the requirement text the pipelines actually send
            assert svc["description"].rstrip(".") in to_benchmark_workflow(task).natural_language_requirement
