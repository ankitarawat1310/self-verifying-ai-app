"""OllamaLLMProvider against a fake Ollama server (no GPU or network needed)."""
from __future__ import annotations

import json

import httpx
import pytest

from shared.budget.tracker import BudgetTracker
from shared.llm.provider import OllamaLLMProvider


def _fake_ollama(captured: list[dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        body = json.loads(request.content)
        captured.append(body)
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": json.dumps({"app_code": "x", "test_code": "y"})},
                "prompt_eval_count": 120,
                "eval_count": 30,
                "total_duration": 2_500_000_000,
                "load_duration": 100_000_000,
                "done_reason": "stop",
            },
        )

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("OLLAMA_MODEL", "OLLAMA_BASE_URL", "OLLAMA_NUM_CTX", "OLLAMA_KEEP_ALIVE", "SVAGA_SEED"):
        monkeypatch.delenv(key, raising=False)


def test_defaults_and_v1_suffix_is_stripped(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    provider = OllamaLLMProvider(transport=_fake_ollama([]))
    assert provider.model == "qwen3-coder:30b"
    assert provider.base_url == "http://127.0.0.1:11434"


def test_schema_keep_alive_seed_and_usage(monkeypatch):
    monkeypatch.setenv("SVAGA_SEED", "7")
    captured: list[dict] = []
    provider = OllamaLLMProvider(transport=_fake_ollama(captured))
    schema = {"type": "object", "properties": {"app_code": {"type": "string"}}, "required": ["app_code"]}
    budget = BudgetTracker()

    result = provider.complete_json("sys", "user", budget=budget, schema=schema)

    assert result == {"app_code": "x", "test_code": "y"}
    sent = captured[0]
    assert sent["format"] == schema
    assert sent["stream"] is False
    assert sent["keep_alive"] == "24h"
    assert sent["options"]["seed"] == 7
    assert sent["options"]["num_ctx"] == 16384
    assert budget.tokens_used == 150 and budget.llm_calls == 1
    assert provider.last_usage["input_tokens"] == 120
    assert provider.last_usage["output_tokens"] == 30
    assert provider.last_usage["total_seconds"] == 2.5


def test_without_schema_requests_plain_json():
    captured: list[dict] = []
    provider = OllamaLLMProvider(transport=_fake_ollama(captured))
    provider.complete_json("sys", "user")
    assert captured[0]["format"] == "json"
    assert "seed" not in captured[0]["options"]
