"""api_fuzz must run the generated app as a real module so body-model routes resolve their own types."""
from svaga_platform.app.verification.fuzz_runner import run_api_fuzz

APP = '''
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field
from enum import Enum
from typing import Any

app = FastAPI()

class Kind(str, Enum):
    A = "a"

class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Kind = Kind.A
    name: str = Field(min_length=1)
    payload: dict[str, Any] = {}

class ItemOut(BaseModel):
    kind: Kind
    name: str

@app.post("/items", status_code=201)
def create(request: Item) -> ItemOut:
    return ItemOut(kind=request.kind, name=request.name)
'''


def test_body_model_routes_do_not_fail_with_typeadapter_error():
    result = run_api_fuzz(APP, {"endpoints": [{"path": "/items", "method": "POST"}]})
    assert result.passed, result.failures
    assert result.attempts > 0


def test_fuzz_still_reports_real_server_errors():
    broken = APP + "\n@app.get('/boom')\ndef boom():\n    return 1 / 0\n"
    result = run_api_fuzz(broken, {"endpoints": [{"path": "/boom", "method": "GET"}]})
    assert not result.passed


def test_fuzz_does_not_leak_modules():
    import sys
    before = {m for m in sys.modules if m.startswith("_svaga_fuzz_")}
    run_api_fuzz(APP, {"endpoints": [{"path": "/items", "method": "POST"}]})
    assert {m for m in sys.modules if m.startswith("_svaga_fuzz_")} == before
