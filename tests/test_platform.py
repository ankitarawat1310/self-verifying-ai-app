import os

import pytest

from shared.benchmarks.loader import load_all_benchmarks
from shared.budget.tracker import BudgetProfile, BudgetTracker
from shared.llm.provider import ScriptedLLMProvider
from shared.policy.checker import PolicyDocument, check_policy_static
from shared.sandbox.pytest_runner import execute_pytest_sandbox
from svaga_platform.app.pipelines.registry import get_pipeline
from svaga_platform.app.release_gate import evaluate_release_gate
from svaga_platform.app.verification.orchestrator import VerificationReport, run_full_verification
from svaga_platform.app.artifacts import PipelineArtifacts
from shared.schemas.workflow_spec import WorkflowSpecDocument, ActorSpec, EndpointSpec


def test_scripted_llm_generates_passing_tests():
    llm = ScriptedLLMProvider()
    out = llm.complete_json("generate app_code and test_code", "URL shortener /shorten")
    assert "app_code" in out and "test_code" in out
    res = execute_pytest_sandbox(out["app_code"], out["test_code"])
    assert res.passed, res.stderr or res.stdout


def test_policy_static_blocks_subprocess():
    code = "import subprocess\nsubprocess.call(['ls'])"
    pol = PolicyDocument()
    result = check_policy_static(code, pol)
    assert not result.passed


def test_release_gate_accepts_clean_report():
    report = VerificationReport(passed=True, verifiers=[{"name": "pytest_sandbox", "passed": True}], counterexamples=[])
    gate = evaluate_release_gate(report, spec_hash="abc", frozen_spec_hash="abc", policy_passed=True)
    assert gate.decision == "ACCEPT"


@pytest.mark.parametrize("pipe_name", ["m1", "m2", "m3", "m4"])
def test_pipelines_url_shortener(pipe_name):
    benchmarks = {b.workflow_id: b for b in load_all_benchmarks()}
    assert "url_shortener" in benchmarks
    pipeline = get_pipeline(pipe_name)
    budget = BudgetTracker(profile=BudgetProfile(max_llm_calls=50, max_repair_rounds=3))
    result = pipeline.run(benchmarks["url_shortener"], budget=budget)
    assert result.artifacts.app_code
    assert result.verification["passed"] or result.decision in ("ACCEPT", "REJECT")


def test_m1_pipeline_accept_on_url_shortener():
    benchmarks = {b.workflow_id: b for b in load_all_benchmarks()}
    pipeline = get_pipeline("m1")
    budget = BudgetTracker(profile=BudgetProfile(max_llm_calls=50))
    result = pipeline.run(benchmarks["url_shortener"], budget=budget)
    assert result.decision == "ACCEPT"


def test_benchmark_count_at_least_20():
    assert len(load_all_benchmarks()) >= 20


def test_model1_generate_endpoint():
    os.environ["SVAGA_SCRIPTED_LLM"] = "1"
    from fastapi.testclient import TestClient
    from svaga_platform.app.main import app

    client = TestClient(app)
    res = client.post("/api/v1/generate-model1", json={"prompt": "URL shortener"})
    assert res.status_code == 200
    body = res.json()
    assert body["verified"] is True
    assert "app_code" in body
