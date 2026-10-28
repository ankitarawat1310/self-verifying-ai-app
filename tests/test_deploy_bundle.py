import json
import zipfile
from io import BytesIO
from pathlib import Path

from shared.generation.deploy_bundle import (
    build_readme,
    is_url_shortener_spec,
    prepare_artifacts_from_disk,
    refresh_artifact_sources,
)
from svaga_platform.app.run_store import build_zip, persist_run


def test_refresh_injects_url_shortener_ui():
    spec = {
        "workflow_id": "url_shortener",
        "application_name": "URL Shortener",
        "endpoints": [
            {"method": "POST", "path": "/shorten"},
            {"method": "GET", "path": "/r/{code}"},
        ],
    }
    app_code = '''
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
app = FastAPI()
_store = {}
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
    code = res.json()["code"]
    got = client.get(f"/r/{code}")
    assert got.status_code == 200
    assert got.json()["url"] == "https://example.com"
'''
    app, tests = refresh_artifact_sources(app_code, test_code, spec)
    assert "_SVAGA_URL_SHORTENER_PAGE" in app
    assert "follow_redirects=False" in tests


def test_build_zip_includes_run_script_and_ui(tmp_path, monkeypatch):
    from shared import paths

    monkeypatch.setattr(paths, "RESULTS_DIR", tmp_path)
    run_id = "testrun123"
    spec = {
        "workflow_id": "url_shortener",
        "application_name": "URL Shortener",
        "description": "Shorten URLs",
        "endpoints": [
            {"method": "POST", "path": "/shorten"},
            {"method": "GET", "path": "/r/{code}"},
        ],
    }
    minimal_app = '''
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
app = FastAPI()
_store = {}
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
    persist_run(
        run_id,
        {
            "artifacts": {
                "app.py": minimal_app,
                "test_app.py": "from app import app\n",
                "workflow_spec.json": json.dumps(spec),
                "policy.json": "{}",
            }
        },
    )
    data = build_zip(run_id)
    zf = zipfile.ZipFile(BytesIO(data))
    names = set(zf.namelist())
    assert "run.ps1" in names
    assert "requirements.txt" in names
    assert "README.md" in names
    assert "_SVAGA_URL_SHORTENER_PAGE" in zf.read("app.py").decode()


def test_readme_mentions_browser_for_shortener():
    spec = {"workflow_id": "url_shortener", "application_name": "URL Shortener"}
    assert is_url_shortener_spec(spec)
    text = build_readme(spec)
    assert "paste a long URL" in text.lower() or "paste" in text.lower()


def test_bundle_requirements_include_pydantic_email_extra():
    """A downloaded app that uses pydantic's EmailStr must run standalone, so the email extra has to be installed."""
    from shared.generation.deploy_bundle import REQUIREMENTS_TXT
    from shared.policy.checker import PolicyDocument
    from svaga_platform.app.artifacts import PipelineArtifacts

    assert "pydantic[email]>=2.0" in REQUIREMENTS_TXT.splitlines()
    assert any(line.split("#")[0].strip() == "tzdata" for line in REQUIREMENTS_TXT.splitlines())
    files = PipelineArtifacts(
        app_code="from fastapi import FastAPI\napp = FastAPI()\n",
        test_code="",
        workflow_spec={"workflow_id": "x", "application_name": "X"},
        policy=PolicyDocument(),
    ).to_files()
    assert files["requirements.txt"] == REQUIREMENTS_TXT


def test_generated_app_gets_a_working_web_ui():
    """Sep 26: the generated apps had only /docs. Every app now serves a form-based UI at / and /ui."""
    from fastapi.testclient import TestClient
    import types

    from shared.generation.simple_ui import finalize_generated_app

    app_code = (
        "from fastapi import FastAPI, Header\nfrom pydantic import BaseModel\nfrom typing import Optional\n"
        "app = FastAPI()\nITEMS = {}\n"
        "class ItemIn(BaseModel):\n    name: str\n"
        "@app.post('/items', status_code=201)\n"
        "def create(body: ItemIn, x_actor_id: Optional[str] = Header(None, alias='x-actor-id')):\n"
        "    ITEMS[str(len(ITEMS)+1)] = {'id': str(len(ITEMS)+1), 'name': body.name}\n    return ITEMS[str(len(ITEMS))]\n"
        "@app.get('/items')\ndef list_items():\n    return list(ITEMS.values())\n"
    )
    spec = {"workflow_id": "t", "application_name": "Item list", "description": "Keep a list.\n\nPublic interface ...",
            "actors": [{"id": "clerk", "name": "Clerk"}],
            "endpoints": [{"method": "POST", "path": "/items", "business_action": "Add an item", "allowed_roles": ["clerk"]}]}
    code = finalize_generated_app(app_code, spec)
    assert finalize_generated_app(code, spec) == code  # idempotent
    mod = types.ModuleType("gen_ui_app")
    exec(compile(code, "<gen>", "exec", dont_inherit=True), mod.__dict__)
    c = TestClient(mod.app)
    for path in ("/", "/ui"):
        r = c.get(path)
        assert r.status_code == 200 and "text/html" in r.headers["content-type"]
        assert "Item list" in r.text and "Add an item" in r.text and "clerk" in r.text
        assert "Public interface" not in r.text
    assert "/ui" not in c.get("/openapi.json").json()["paths"]  # the UI never changes the API contract
    assert c.get("/health").status_code == 200
    assert c.post("/items", json={"name": "pen"}).status_code == 201


def test_ui_does_not_replace_an_apps_own_root():
    from shared.generation.simple_ui import finalize_generated_app

    code = finalize_generated_app("from fastapi import FastAPI\napp = FastAPI()\n@app.get('/')\ndef home():\n    return {'mine': True}\n", {})
    import types
    from fastapi.testclient import TestClient

    mod = types.ModuleType("gen_ui_app2")
    exec(compile(code, "<gen>", "exec", dont_inherit=True), mod.__dict__)
    c = TestClient(mod.app)
    assert c.get("/").json() == {"mine": True}
    assert "text/html" in c.get("/ui").headers["content-type"]
