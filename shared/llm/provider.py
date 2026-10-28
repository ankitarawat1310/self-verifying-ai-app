from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any

from shared.budget.tracker import BudgetTracker


class LLMProvider(ABC):
    @abstractmethod
    def complete_json(self, system: str, user: str, *, budget: BudgetTracker | None = None) -> dict[str, Any]:
        raise NotImplementedError


class ScriptedLLMProvider(LLMProvider):
    """Deterministic responses for CI and integration tests (alias: FakeLLMProvider)."""

    def complete_json(self, system: str, user: str, *, budget: BudgetTracker | None = None) -> dict[str, Any]:
        if budget:
            budget.record_llm(tokens=500)
        from shared.llm.scripted_templates import (
            fake_spec_from_requirement,
            parse_spec_from_prompt,
            synthesize_from_spec,
            url_shortener_bundle,
        )

        sys_lower = system.lower()
        if "behaviorspec author" in sys_lower and "SKELETON_JSON_BEGIN" in user:
            # M2 spec author: echo the interface skeleton back (a valid, rule-free spec)
            return json.loads(user.split("SKELETON_JSON_BEGIN", 1)[1].split("SKELETON_JSON_END", 1)[0])
        if "frozen behaviorspec" in sys_lower:
            # M2 synthesizer: stub routes for every operation in the frozen spec
            body = user.split("Frozen BehaviorSpec", 1)[1].split("\n", 1)[1].split("\n\nReference context:", 1)[0]
            ops = json.loads(body).get("operations", [])
            endpoints = [{"method": o["route"].split(" ", 1)[0], "path": o["route"].split(" ", 1)[1]} for o in ops]
            return {"app_code": synthesize_from_spec({"workflow_id": "m2_app", "endpoints": endpoints})["app_code"]}
        if "spec author" in sys_lower or "workflowspec author" in sys_lower:
            return fake_spec_from_requirement(user)
        if "repair" in sys_lower or "counterexample" in sys_lower:
            base = synthesize_from_spec(parse_spec_from_prompt(user) or {"workflow_id": "url_shortener", "endpoints": []})
            base["patch"] = base["app_code"]
            return base
        if "test_properties" in sys_lower or "hypothesis" in sys_lower:
            return _fake_property_tests()
        spec = parse_spec_from_prompt(user)
        if spec:
            return synthesize_from_spec(spec)
        user_lower = user.lower()
        if "url short" in user_lower or "/shorten" in user_lower:
            return url_shortener_bundle()
        return synthesize_from_spec(
            {"workflow_id": "custom_app", "application_name": "Custom App", "endpoints": [{"method": "GET", "path": "/health"}]}
        )


def _parse_json_content(content: str) -> dict[str, Any]:
    text = (content or "{}").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def _chat_json_completion(client: Any, *, model: str, system: str, user: str) -> tuple[str, int]:
    messages = [
        {"role": "system", "content": system + "\n\nRespond with a single valid JSON object only."},
        {"role": "user", "content": user},
    ]
    try:
        response = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=messages,
        )
    except Exception:
        response = client.chat.completions.create(model=model, messages=messages)
    content = response.choices[0].message.content or "{}"
    usage = response.usage
    tokens = (usage.total_tokens if usage else 0) or 0
    return content, tokens


class OpenAILLMProvider(LLMProvider):
    def __init__(self, model: str = "gpt-4o", embedding_model: str = "text-embedding-3-small"):
        self.model = model
        self.embedding_model = embedding_model
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY required for OpenAILLMProvider")
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)

    def complete_json(self, system: str, user: str, *, budget: BudgetTracker | None = None) -> dict[str, Any]:
        content, tokens = _chat_json_completion(
            self.client, model=self.model, system=system, user=user
        )
        if budget:
            budget.record_llm(tokens=tokens)
        return _parse_json_content(content)


class OllamaLLMProvider(LLMProvider):
    """Local inference through Ollama's native /api/chat endpoint.

    Uses the native API (not the OpenAI-compatible /v1 layer) because it supports:
    - ``format``: a JSON schema the reply must follow (structured output), or "json";
    - ``keep_alive``: keeps the model loaded between calls (first load of a 30B model takes ~35 s);
    - ``options.seed`` / ``temperature`` / ``num_ctx`` / ``num_predict`` for reproducible runs;
    - exact prompt and output token counts (``prompt_eval_count``, ``eval_count``) for the cost metric.

    Environment (all optional):
      OLLAMA_MODEL (default qwen3-coder:30b), OLLAMA_BASE_URL (default http://127.0.0.1:11434; a trailing /v1 is ignored),
      OLLAMA_NUM_CTX (16384), OLLAMA_NUM_PREDICT (6000), OLLAMA_TEMPERATURE (0.2), OLLAMA_KEEP_ALIVE (24h),
      OLLAMA_TIMEOUT_SECONDS (600), SVAGA_SEED (unset = model default).
    """

    DEFAULT_MODEL = "qwen3-coder:30b"

    def __init__(self, model: str | None = None, base_url: str | None = None, *, transport: Any = None):
        import httpx

        self.model = model or os.getenv("OLLAMA_MODEL") or self.DEFAULT_MODEL
        base = (base_url or os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        self.base_url = base
        self.num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "16384"))
        self.num_predict = int(os.getenv("OLLAMA_NUM_PREDICT", "6000"))
        self.temperature = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
        self.keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "24h")
        seed = os.getenv("SVAGA_SEED", "").strip()
        self.seed = int(seed) if seed else None
        timeout = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "600"))
        self.client = httpx.Client(base_url=self.base_url, timeout=timeout, transport=transport)
        self.last_usage: dict[str, Any] = {}

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        budget: BudgetTracker | None = None,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
            "temperature": self.temperature,
        }
        if self.seed is not None:
            options["seed"] = self.seed
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system + "\n\nRespond with a single valid JSON object only."},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": schema if schema else "json",
            "options": options,
            "keep_alive": self.keep_alive,
        }
        response = self.client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        content = (data.get("message") or {}).get("content") or "{}"
        prompt_tokens = int(data.get("prompt_eval_count") or 0)
        output_tokens = int(data.get("eval_count") or 0)
        self.last_usage = {
            "input_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "total_seconds": round((data.get("total_duration") or 0) / 1e9, 3),
            "load_seconds": round((data.get("load_duration") or 0) / 1e9, 3),
            "done_reason": data.get("done_reason"),
        }
        if budget:
            budget.record_llm(tokens=prompt_tokens + output_tokens)
        return _parse_json_content(content)


DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5"


class AnthropicLLMProvider(LLMProvider):
    """Claude via the official Anthropic SDK. Credentials come from ANTHROPIC_API_KEY (or the SDK's other sources).

    Defaults to Haiku 4.5 (cheapest/fastest current Claude model); override with ANTHROPIC_MODEL.
    """

    max_tokens = 16000  # non-streaming ceiling; large enough for an app + tests without hitting SDK timeouts

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL
        from anthropic import Anthropic

        self.client = Anthropic()

    def complete_json(self, system: str, user: str, *, budget: BudgetTracker | None = None) -> dict[str, Any]:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system + "\n\nRespond with a single valid JSON object only.",
            messages=[{"role": "user", "content": user}],
        )
        content = "".join(block.text for block in response.content if block.type == "text")
        if budget:
            budget.record_llm(tokens=response.usage.input_tokens + response.usage.output_tokens)
        return _parse_json_content(content)


FakeLLMProvider = ScriptedLLMProvider


def get_llm_provider() -> LLMProvider:
    scripted = os.getenv("SVAGA_SCRIPTED_LLM", "").lower() in ("1", "true", "yes")
    legacy_llm = os.getenv("SVAGA_LLM", "").lower()
    provider = os.getenv("SVAGA_LLM_PROVIDER", "").lower()

    if scripted or legacy_llm in ("fake", "scripted"):
        return ScriptedLLMProvider()

    if provider == "ollama" or legacy_llm == "ollama":
        return OllamaLLMProvider()

    if provider == "anthropic" or legacy_llm == "anthropic":
        return AnthropicLLMProvider()

    if provider == "openai" or os.getenv("OPENAI_API_KEY"):
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        embedding = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        return OpenAILLMProvider(model=model, embedding_model=embedding)

    return ScriptedLLMProvider()


def describe_llm_provider(provider: LLMProvider | None = None) -> dict[str, str]:
    provider = provider or get_llm_provider()
    if isinstance(provider, ScriptedLLMProvider):
        return {"provider": "scripted", "model": "ScriptedLLMProvider"}
    if isinstance(provider, OllamaLLMProvider):
        return {"provider": "ollama", "model": provider.model}
    if isinstance(provider, AnthropicLLMProvider):
        return {"provider": "anthropic", "model": provider.model}
    if isinstance(provider, OpenAILLMProvider):
        return {"provider": "openai", "model": provider.model}
    return {"provider": "unknown", "model": type(provider).__name__}


def _fake_property_tests() -> dict[str, Any]:
    content = '''
from hypothesis import given, strategies as st
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

@given(st.text(min_size=1, max_size=40).filter(lambda s: "/" not in s))
def test_shorten_accepts_strings(url):
    res = client.post("/shorten", json={"url": url})
    assert res.status_code == 200
'''
    return {"test_properties_code": content.strip()}


