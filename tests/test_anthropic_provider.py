"""AnthropicLLMProvider behaviour against a stubbed SDK client (no network, no API key)."""
import json
from types import SimpleNamespace

import pytest

import anthropic
from shared.benchmarks.loader import load_all_benchmarks
from shared.budget.tracker import BudgetProfile, BudgetTracker
from shared.llm.provider import (
    DEFAULT_ANTHROPIC_MODEL,
    AnthropicLLMProvider,
    ScriptedLLMProvider,
    describe_llm_provider,
    get_llm_provider,
)
from shared.llm.scripted_templates import url_shortener_bundle
from svaga_platform.app.pipelines.registry import get_pipeline  # import first: avoids a circular import


class StubAnthropic:
    """Stands in for anthropic.Anthropic; returns ``StubAnthropic.blocks`` for every request."""

    blocks: list = []
    usage = SimpleNamespace(input_tokens=100, output_tokens=40)
    calls: list = []

    def __init__(self, *args, **kwargs):
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        StubAnthropic.calls.append(kwargs)
        return SimpleNamespace(content=StubAnthropic.blocks, usage=StubAnthropic.usage, stop_reason="end_turn")


def text(s: str):
    return SimpleNamespace(type="text", text=s)


@pytest.fixture(autouse=True)
def stub_sdk(monkeypatch):
    StubAnthropic.calls = []
    StubAnthropic.blocks = [text('{"ok": true}')]
    monkeypatch.setattr(anthropic, "Anthropic", StubAnthropic)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    # svaga_platform/tests/conftest.py sets SVAGA_LLM=fake at collection; the legacy flag outranks SVAGA_LLM_PROVIDER
    monkeypatch.delenv("SVAGA_LLM", raising=False)


def test_complete_json_parses_and_sends_expected_request():
    out = AnthropicLLMProvider().complete_json("You are X.", "do it")
    assert out == {"ok": True}
    call = StubAnthropic.calls[0]
    assert call["model"] == DEFAULT_ANTHROPIC_MODEL == "claude-haiku-4-5"
    assert call["system"].startswith("You are X.") and "single valid JSON object" in call["system"]
    assert call["messages"] == [{"role": "user", "content": "do it"}]
    assert isinstance(call["max_tokens"], int) and call["max_tokens"] > 0
    assert "thinking" not in call and "temperature" not in call


def test_fenced_json_is_parsed():
    StubAnthropic.blocks = [text('```json\n{"a": 1}\n```')]
    assert AnthropicLLMProvider().complete_json("s", "u") == {"a": 1}


def test_non_text_blocks_are_skipped_and_text_blocks_joined():
    StubAnthropic.blocks = [SimpleNamespace(type="thinking", thinking="hmm"), text('{"a":'), text(' 2}')]
    assert AnthropicLLMProvider().complete_json("s", "u") == {"a": 2}


def test_records_tokens_on_budget():
    budget = BudgetTracker(profile=BudgetProfile(max_llm_calls=5))
    AnthropicLLMProvider().complete_json("s", "u", budget=budget)
    assert budget.llm_calls == 1 and budget.tokens_used == 140


def test_invalid_json_raises_valueerror():
    StubAnthropic.blocks = [text("sorry, I can't do that")]
    with pytest.raises(ValueError):
        AnthropicLLMProvider().complete_json("s", "u")


def test_model_override_env_and_argument(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-5")
    assert AnthropicLLMProvider().model == "claude-sonnet-5"
    assert AnthropicLLMProvider(model="claude-opus-5").model == "claude-opus-5"


def test_get_llm_provider_selects_anthropic(monkeypatch):
    monkeypatch.setenv("SVAGA_SCRIPTED_LLM", "0")
    monkeypatch.setenv("SVAGA_LLM_PROVIDER", "anthropic")
    provider = get_llm_provider()
    assert isinstance(provider, AnthropicLLMProvider)
    assert describe_llm_provider(provider) == {"provider": "anthropic", "model": "claude-haiku-4-5"}


def test_scripted_flag_still_wins_over_provider(monkeypatch):
    monkeypatch.setenv("SVAGA_SCRIPTED_LLM", "1")
    monkeypatch.setenv("SVAGA_LLM_PROVIDER", "anthropic")
    assert isinstance(get_llm_provider(), ScriptedLLMProvider)


def _run_m1(monkeypatch, workflow_id="url_shortener"):
    monkeypatch.setattr("svaga_platform.app.pipelines.m1_rag.get_llm_provider", lambda: AnthropicLLMProvider())
    bench = {b.workflow_id: b for b in load_all_benchmarks()}[workflow_id]
    return get_pipeline("m1").run(bench, budget=BudgetTracker(profile=BudgetProfile(max_llm_calls=50)))


def test_m1_accepts_valid_claude_style_generation(monkeypatch):
    StubAnthropic.blocks = [text("```json\n" + json.dumps(url_shortener_bundle()) + "\n```")]
    result = _run_m1(monkeypatch)
    assert result.decision == "ACCEPT"
    assert result.budget["llm_calls"] >= 2 and result.budget["tokens_used"] > 0


def test_m1_rejects_when_claude_returns_wrong_shape(monkeypatch):
    StubAnthropic.blocks = [text('{"hello": "world"}')]
    result = _run_m1(monkeypatch)
    assert result.decision == "REJECT"
    assert result.metadata["gate_reasons"][0].startswith("malformed generation output")
