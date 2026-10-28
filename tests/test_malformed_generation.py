"""M1 must turn malformed LLM generation output into a REJECT, never an exception."""
import json

import pytest

from model1_rag_generator.backend.app import generator
from model1_rag_generator.backend.app.generator import MALFORMED_PREFIX, generate_code_and_tests, validate_generation
from shared.benchmarks.loader import load_all_benchmarks
from shared.budget.tracker import BudgetExceeded, BudgetProfile, BudgetTracker
from shared.llm.provider import ScriptedLLMProvider
from svaga_platform.app.pipelines.registry import get_pipeline  # import first: avoids a circular import
from svaga_platform.app.spec_from_nl import generate_spec_from_nl

SPEC_ECHO = {
    "workflow_id": "url_shortener",
    "application_name": "URL Shortener",
    "description": "x",
    "actors": [],
    "entities": [],
    "business_rules": [],
    "endpoints": [],
    "invariants": [],
}


class CodegenStub(ScriptedLLMProvider):
    """Scripted for the spec/policy calls; the code-generation call returns/raises ``response``."""

    def __init__(self, response=None, exc: Exception | None = None):
        self.response = response
        self.exc = exc

    def complete_json(self, system, user, *, budget=None):
        if system == generator.SYSTEM:
            if self.exc:
                raise self.exc
            return self.response
        return super().complete_json(system, user, budget=budget)


MALFORMED_CASES = {
    "missing_app_code": ({"test_code": "def test_x(): pass"}, "missing required key(s): app_code"),
    "missing_test_code": ({"app_code": "x = 1"}, "missing required key(s): test_code"),
    "missing_both": ({"foo": "bar"}, "missing required key(s): app_code, test_code"),
    "workflow_spec_echo": (SPEC_ECHO, "echoed the WorkflowSpec"),
    "empty_object": ({}, "missing required key(s): app_code, test_code"),
    "not_an_object": (["app_code", "test_code"], "expected a JSON object, got list"),
    "null": (None, "expected a JSON object, got NoneType"),
    "empty_app_code": ({"app_code": "  ", "test_code": "def test_x(): pass"}, "'app_code' is empty"),
    "non_string_test_code": ({"app_code": "x = 1", "test_code": {"a": 1}}, "'test_code' must be a string, got dict"),
}


def _run_m1(llm, monkeypatch, workflow_id="url_shortener"):
    monkeypatch.setattr("svaga_platform.app.pipelines.m1_rag.get_llm_provider", lambda: llm)
    bench = {b.workflow_id: b for b in load_all_benchmarks()}[workflow_id]
    return get_pipeline("m1").run(bench, budget=BudgetTracker(profile=BudgetProfile(max_llm_calls=50)))


@pytest.mark.parametrize("name", MALFORMED_CASES)
def test_m1_rejects_malformed_generation(name, monkeypatch):
    response, expected = MALFORMED_CASES[name]
    result = _run_m1(CodegenStub(response), monkeypatch)

    assert result.decision == "REJECT"
    reasons = result.metadata["gate_reasons"]
    assert len(reasons) == 1 and reasons[0].startswith(MALFORMED_PREFIX)
    assert expected in reasons[0]
    assert result.metadata["malformed_generation"] is True
    assert result.counterexamples and result.counterexamples[0]["property_id"] == "generation_output"
    assert result.verification["passed"] is False
    assert [v["name"] for v in result.verification["verifiers"]] == ["generation_output"]
    assert result.artifacts.app_code == "" and result.artifacts.test_code == ""
    json.dumps(result.to_dict())  # must stay serializable for the API / run store


def test_m1_rejects_non_json_response(monkeypatch):
    result = _run_m1(CodegenStub(exc=json.JSONDecodeError("Expecting value", "not json", 0)), monkeypatch)
    assert result.decision == "REJECT"
    assert "response was not valid JSON" in result.metadata["gate_reasons"][0]


def test_valid_generation_still_accepted(monkeypatch):
    result = _run_m1(ScriptedLLMProvider(), monkeypatch)
    assert result.decision == "ACCEPT"
    assert "malformed_generation" not in result.metadata


def test_budget_exceeded_is_not_swallowed(monkeypatch):
    with pytest.raises(BudgetExceeded):
        _run_m1(CodegenStub(exc=BudgetExceeded("LLM call budget exceeded")), monkeypatch)


def test_validate_generation_keeps_valid_payload_untouched():
    payload = {"app_code": "x = 1", "test_code": "def test_x(): pass", "extra": 1}
    assert validate_generation(payload) is payload


def test_generate_code_and_tests_never_raises_on_bad_json():
    out = generate_code_and_tests("p", "ctx", llm=CodegenStub(exc=json.JSONDecodeError("bad", "{", 0)))
    assert out["malformed_reason"].startswith(MALFORMED_PREFIX)
    assert out["app_code"] == "" and out["test_code"] == ""


def test_adhoc_spec_generation_falls_back_on_bad_llm_output():
    bench = {b.workflow_id: b for b in load_all_benchmarks()}["url_shortener"]

    class BadSpecLLM(ScriptedLLMProvider):
        def complete_json(self, system, user, *, budget=None):
            raise json.JSONDecodeError("bad", "{", 0)

    spec = generate_spec_from_nl(BadSpecLLM(), bench)
    assert spec.workflow_id == "url_shortener"
