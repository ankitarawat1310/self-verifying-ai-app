"""Deterministic app/test synthesis from a WorkflowSpec (CI + fallback)."""

from __future__ import annotations

import json
import re
from typing import Any


def parse_spec_from_prompt(user: str) -> dict[str, Any] | None:
    """Extract a WorkflowSpec JSON object embedded in an LLM user prompt."""
    marker = "Frozen WorkflowSpec:"
    if marker in user:
        tail = user.split(marker, 1)[1].strip()
        if "Reference context:" in tail:
            tail = tail.split("Reference context:", 1)[0].strip()
        try:
            return json.loads(tail)
        except json.JSONDecodeError:
            pass
    match = re.search(r'\{\s*"workflow_id"\s*:\s*"[^"]+"[\s\S]*\}', user)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _is_url_shortener_spec(spec: dict[str, Any]) -> bool:
    if spec.get("workflow_id") == "url_shortener":
        return True
    paths = {e.get("path") for e in spec.get("endpoints") or [] if isinstance(e, dict)}
    return "/shorten" in paths and any(p and "/r/" in str(p) for p in paths)


def url_shortener_bundle() -> dict[str, str]:
    app_code = '''
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Generated App")
_store: dict[str, str] = {}

class ShortenRequest(BaseModel):
    url: str = Field(min_length=1)

@app.post("/shorten")
def shorten(body: ShortenRequest):
    code = str(len(_store) + 1)
    _store[code] = body.url
    return {"code": code, "url": body.url}

@app.get("/r/{code}")
def redirect(code: str):
    if code not in _store:
        raise HTTPException(status_code=404, detail="not found")
    return {"url": _store[code]}
'''
    test_code = '''
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def test_shorten_and_redirect():
    res = client.post("/shorten", json={"url": "https://example.com"})
    assert res.status_code == 200
    code = res.json()["code"]
    got = client.get(f"/r/{code}")
    assert got.status_code == 200
    assert got.json()["url"] == "https://example.com"

def test_missing_code_404():
    assert client.get("/r/missing").status_code == 404
'''
    return {"app_code": app_code.strip(), "test_code": test_code.strip()}


def synthesize_from_spec(spec: dict[str, Any]) -> dict[str, str]:
    if _is_url_shortener_spec(spec):
        return url_shortener_bundle()

    title = spec.get("application_name") or spec.get("workflow_id") or "Generated App"
    endpoints = [e for e in (spec.get("endpoints") or []) if isinstance(e, dict)]
    if not endpoints:
        endpoints = [{"method": "GET", "path": "/health", "business_action": "health"}]

    route_blocks: list[str] = []
    test_blocks: list[str] = ["from fastapi.testclient import TestClient", "from app import app", "", "client = TestClient(app)", ""]

    for ep in endpoints:
        method = str(ep.get("method", "GET")).upper()
        path = str(ep.get("path", "/health"))
        action = ep.get("business_action") or "handler"
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", f"{method}_{path}")
        if method == "GET" and "{" not in path:
            route_blocks.append(
                f'@app.get("{path}")\n'
                f"def {safe_name}():\n"
                f'    return {{"workflow_id": "{spec.get("workflow_id", "app")}", "action": "{action}", "status": "ok"}}'
            )
            test_blocks.append(
                f"def test_{safe_name}():\n"
                f'    res = client.get("{path}")\n'
                f"    assert res.status_code == 200\n"
                f'    assert res.json().get("status") == "ok"'
            )
        elif method == "GET" and "{" in path:
            param = path.split("{")[1].split("}")[0]
            route_blocks.append(
                f'@app.get("{path}")\n'
                f"def {safe_name}({param}: str):\n"
                f'    return {{"{param}": {param}, "status": "ok"}}'
            )
            test_blocks.append(
                f"def test_{safe_name}():\n"
                f'    res = client.get("{path.replace("{" + param + "}", "sample")}")\n'
                f"    assert res.status_code == 200"
            )
        elif method == "POST":
            route_blocks.append(
                f'@app.post("{path}")\n'
                f"def {safe_name}(payload: dict | None = None):\n"
                f'    return {{"received": payload or {{}}, "status": "created", "action": "{action}"}}'
            )
            test_blocks.append(
                f"def test_{safe_name}():\n"
                f'    res = client.post("{path}", json={{"sample": True}})\n'
                f"    assert res.status_code == 200\n"
                f'    assert res.json().get("status") == "created"'
            )

    app_code = (
        "from fastapi import FastAPI\n\n"
        f'app = FastAPI(title="{title}")\n\n'
        + "\n\n".join(route_blocks)
    )
    test_code = "\n\n".join(test_blocks)
    return {"app_code": app_code.strip(), "test_code": test_code.strip()}


def fake_spec_from_requirement(user: str) -> dict[str, Any]:
    """Scripted WorkflowSpec author — prefer benchmark id embedded in prompt."""
    parsed = parse_spec_from_prompt(user)
    if parsed and parsed.get("workflow_id"):
        return parsed
    lower = user.lower()
    if "url short" in lower or "/shorten" in lower:
        return {
            "workflow_id": "url_shortener",
            "application_name": "URL Shortener",
            "description": "Shorten URLs and resolve redirects.",
            "actors": [{"id": "user", "name": "User", "permissions": ["shorten", "resolve"]}],
            "entities": [{"name": "Link", "fields": [{"name": "url", "type": "string"}]}],
            "business_rules": [{"id": "unique_code", "description": "Each code maps to one URL"}],
            "endpoints": [
                {"method": "POST", "path": "/shorten", "business_action": "create_short_link"},
                {"method": "GET", "path": "/r/{code}", "business_action": "resolve"},
            ],
            "invariants": ["codes are immutable once assigned"],
        }
    wid_match = re.search(r"workflow_id[=:\s]+([a-z0-9_]+)", user, re.I)
    wid = wid_match.group(1) if wid_match else "custom_app"
    return {
        "workflow_id": wid,
        "application_name": wid.replace("_", " ").title(),
        "description": user.strip()[:500],
        "actors": [{"id": "user", "name": "User"}],
        "entities": [],
        "business_rules": [],
        "endpoints": [
            {"method": "GET", "path": "/health", "business_action": "health"},
            {"method": "POST", "path": "/items", "business_action": "create"},
            {"method": "GET", "path": "/items", "business_action": "list"},
        ],
        "invariants": [],
    }
