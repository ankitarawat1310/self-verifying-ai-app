"""Route injection into generated FastAPI apps: no duplicate /health, and multi-line app constructors survive."""
import ast

import pytest
from fastapi.testclient import TestClient

from shared.generation.app_bootstrap import (
    defines_route,
    ensure_fastapi_health_route,
    ensure_fastapi_welcome_routes,
)
from shared.generation.simple_ui import finalize_generated_app

MODEL_HEALTH = '@app.get("/health")\ndef health():\n    return {"status": "healthy"}\n'

SINGLE_LINE = 'from fastapi import FastAPI\n\napp = FastAPI()\n\n'
MULTI_LINE = (
    "from fastapi import FastAPI\n\n"
    "app = FastAPI(\n"
    '    title="Doc Approval",\n'
    '    description="multi\\nline",\n'
    ")\n\n"
)


def _client(code: str) -> TestClient:
    ast.parse(code)  # must always be valid Python
    ns: dict = {}
    exec(compile(code, "<generated>", "exec"), ns)
    return TestClient(ns["app"])


def _health_route_count(code: str) -> int:
    count = 0
    for n in ast.walk(ast.parse(code)):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            values = [a.value for a in n.args[:1] if isinstance(a, ast.Constant)]
            values += [k.value.value for k in n.keywords if k.arg == "path" and isinstance(k.value, ast.Constant)]
            count += "/health" in values
    return count


@pytest.mark.parametrize(
    "decorator",
    [
        '@app.get("/health")\ndef h():\n    return {"status": "healthy"}\n',
        "@app.get('/health')\ndef h():\n    return {\"status\": \"healthy\"}\n",
        '@app.get("/health", tags=["ops"])\ndef h():\n    return {"status": "healthy"}\n',
        '@app.get(\n    "/health",\n    tags=["ops"],\n)\nasync def h():\n    return {"status": "healthy"}\n',
        '@app.get(path="/health")\ndef h():\n    return {"status": "healthy"}\n',
        '@app.api_route("/health", methods=["GET"])\ndef h():\n    return {"status": "healthy"}\n',
    ],
)
@pytest.mark.parametrize("ensure", [ensure_fastapi_welcome_routes, ensure_fastapi_health_route])
@pytest.mark.parametrize("prefix", [SINGLE_LINE, MULTI_LINE])
def test_existing_health_route_is_not_duplicated_or_shadowed(ensure, prefix, decorator):
    code = ensure(prefix + decorator)
    assert _health_route_count(code) == 1
    assert "_svaga_health" not in code
    assert _client(code).get("/health").json() == {"status": "healthy"}  # the model's payload, not ours


def test_add_api_route_counts_as_existing_health():
    code = SINGLE_LINE + 'def h():\n    return {"status": "healthy"}\n\napp.add_api_route("/health", h)\n'
    assert defines_route(code, "/health")
    assert "_svaga_health" not in ensure_fastapi_welcome_routes(code)


def test_health_in_comment_or_string_is_not_a_route():
    code = SINGLE_LINE + '# @app.get("/health") would go here\nNOTE = \'@app.get("/health")\'\n'
    assert not defines_route(code, "/health")
    out = ensure_fastapi_health_route(code)
    assert _client(out).get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("ensure", [ensure_fastapi_welcome_routes, ensure_fastapi_health_route])
def test_multiline_constructor_is_not_split(ensure):
    code = ensure(MULTI_LINE + '@app.get("/items")\ndef items():\n    return []\n')
    client = _client(code)  # would raise SyntaxError if the injection landed inside app = FastAPI(...)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/items").json() == []
    assert MULTI_LINE.rstrip() in code  # the constructor text is still one contiguous, unmodified block
    assert code.index("_svaga_health") > code.index(MULTI_LINE.rstrip()) + len(MULTI_LINE.rstrip())


def test_welcome_adds_root_and_health_when_both_missing():
    client = _client(ensure_fastapi_welcome_routes(MULTI_LINE))
    assert client.get("/").json()["status"] == "ok"
    assert client.get("/health").json() == {"status": "ok"}


def test_welcome_adds_only_health_when_root_exists():
    code = ensure_fastapi_welcome_routes(SINGLE_LINE + '@app.get("/")\ndef root():\n    return {"hi": 1}\n')
    client = _client(code)
    assert client.get("/").json() == {"hi": 1}
    assert client.get("/health").json() == {"status": "ok"}


def test_no_app_statement_appends_at_end():
    code = "from fastapi import FastAPI\n\ndef make():\n    return FastAPI()\n\napp = make()\n"
    out = ensure_fastapi_health_route(code)
    assert out.startswith(code) and out.rstrip().endswith('return {"status": "ok"}')
    assert _client(out).get("/health").json() == {"status": "ok"}


def test_unparseable_code_is_appended_to_not_rewritten():
    broken = "from fastapi import FastAPI\napp = FastAPI(\n    title='x'\n\n@app.get('/x')\n"
    out = ensure_fastapi_health_route(broken)
    assert out.startswith(broken)  # original text untouched; nothing spliced into it
    assert ensure_fastapi_health_route(broken + '\n@app.get("/health")\ndef h(): ...\n').count("_svaga_health") == 0


def test_annotated_app_assignment_is_found():
    code = "from fastapi import FastAPI\n\napp: FastAPI = FastAPI(\n    title='x',\n)\n"
    assert _client(ensure_fastapi_health_route(code)).get("/health").status_code == 200


def test_no_trailing_newline_after_constructor():
    out = ensure_fastapi_health_route("from fastapi import FastAPI\napp = FastAPI(\n    title='x',\n)")
    assert _client(out).get("/health").status_code == 200


def test_finalize_generated_app_generic_spec_keeps_model_health_and_multiline_app():
    spec = {"workflow_id": "document_approval", "application_name": "Document Approval", "description": "d"}
    code = MULTI_LINE + MODEL_HEALTH + '\n@app.post("/documents")\ndef create():\n    return {"id": 1}\n'
    out = finalize_generated_app(code, spec)
    client = _client(out)
    assert _health_route_count(out) == 1
    assert client.get("/health").json() == {"status": "healthy"}
    assert client.post("/documents").json() == {"id": 1}
