"""Smoke test for OllamaLLMProvider against a running local Ollama.

Usage (PowerShell, from the SVAGA 3.0 folder):
    .\.venv\Scripts\python.exe scripts\test_ollama_provider.py

Checks: the model answers, the reply follows a JSON schema, and token/time usage is reported.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.budget.tracker import BudgetTracker
from shared.llm.provider import OllamaLLMProvider

SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string"},
        "n": {"type": "integer"},
        "app_code": {"type": "string"},
    },
    "required": ["status", "n", "app_code"],
}


def main() -> int:
    provider = OllamaLLMProvider()
    print(f"model={provider.model} base_url={provider.base_url} num_ctx={provider.num_ctx} keep_alive={provider.keep_alive}")
    budget = BudgetTracker()
    started = time.monotonic()
    result = provider.complete_json(
        "You are a test assistant.",
        'Return status "ok", n = 42, and app_code = a minimal FastAPI app with GET /health returning {"ok": true}.',
        budget=budget,
        schema=SCHEMA,
    )
    elapsed = time.monotonic() - started
    print("keys:", sorted(result))
    print("usage:", json.dumps(provider.last_usage))
    print(f"wall seconds: {elapsed:.1f}; budget tokens: {budget.tokens_used}")
    ok = result.get("status") == "ok" and result.get("n") == 42 and "FastAPI" in result.get("app_code", "")
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
