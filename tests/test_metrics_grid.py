"""Day 8: metrics definitions and the experiment grid (scripted model, 1 task)."""
from __future__ import annotations

import json

from svaga_platform.app.experiments.metrics import permission_excess, run_flags, summarize


def test_run_flags():
    assert run_flags("ACCEPT", 9, 10) == {"hidden_pass": False, "hidden_rate": 0.9, "false_assurance": True,
                                          "false_rejection": False}
    assert run_flags("REJECT", 10, 10)["false_rejection"] is True
    assert run_flags("ERROR", None, None) == {"hidden_pass": False, "hidden_rate": 0.0, "false_assurance": False,
                                              "false_rejection": False}


def test_permission_excess_counts_network_only_without_an_outside_service():
    code = "import os\nimport httpx\nfrom fastapi import FastAPI\nfrom . import local\n"
    assert permission_excess(code, calls_outside_service=False) == {
        "excess": ["httpx", "os"], "count": 2, "risky": ["os"], "network_without_need": ["httpx"]}
    assert permission_excess(code, calls_outside_service=True)["excess"] == ["os"]


def _rec(model, decision, passed, total, recall=None):
    return {"model": model, "decision": decision, "hidden_passed": passed, "hidden_total": total,
            **run_flags(decision, passed, total), "violation_recall": recall, "budget": {"tokens_used": 100, "llm_calls": 1,
            "verification_seconds": 1.0}, "wall_seconds": 2.0, "permission_excess": {"count": 0}}


def test_summarize_rates():
    rows = summarize([_rec("m0", "ACCEPT", 5, 10, 0.2), _rec("m0", "ACCEPT", 10, 10, 0.4),
                      _rec("m2", "REJECT", 5, 10, 0.6), _rec("m2", "ACCEPT", 10, 10, 0.8)])
    assert rows["m0"]["functional_pass_rate"] == 0.5 and rows["m0"]["false_assurance_rate"] == 0.5
    assert rows["m0"]["broken_shipped_rate"] == 1.0
    assert rows["m2"]["false_assurance_rate"] == 0.0 and rows["m2"]["broken_shipped_rate"] == 0.0
    assert rows["m2"]["violation_recall"] == 0.7


def test_grid_runs_judges_scores_and_resumes(tmp_path, monkeypatch):
    monkeypatch.setenv("SVAGA_SCRIPTED_LLM", "1")
    from svaga_platform.app.experiments.grid import load_records, run_one

    rec = run_one("m2", "crud_contact_directory", 1, tmp_path)
    run_dir = tmp_path / "m2" / "crud_contact_directory" / "r1"
    for name in ("record.json", "app.py", "test_app.py", "behavior_spec.json", "verification.json", "judge.json"):
        assert (run_dir / name).exists(), name
    assert rec["hidden_total"] == 12 and rec["decision"] in ("ACCEPT", "REJECT")
    assert rec["recall_detail"]["bugs"] >= 5 and rec["code_hash"]
    # resume: a second call returns the saved record without re-running
    (run_dir / "record.json").write_text(json.dumps({**rec, "marker": 1}), encoding="utf-8")
    assert run_one("m2", "crud_contact_directory", 1, tmp_path)["marker"] == 1
    assert len(load_records(tmp_path)) == 1


def test_contract_check_reads_live_routes_not_decorator_text():
    """Smoke run Sep 26: M2's expense app wrote "@ app.post(...)", passed 14/14 hidden checks, and was rejected."""
    from shared.schemas.workflow_spec import ActorSpec, EndpointSpec, WorkflowSpecDocument
    from svaga_platform.app.verification.contract_checks import check_contract

    spec = WorkflowSpecDocument(workflow_id="t", application_name="t", actors=[ActorSpec(id="u", name="U")],
                                endpoints=[EndpointSpec(method="POST", path="/items", business_action="c"),
                                           EndpointSpec(method="GET", path="/items/{item_id}", business_action="r")])
    code = ("from fastapi import FastAPI, APIRouter\napp = FastAPI()\nr = APIRouter()\n"
            "@ app.post('/items')\ndef c():\n    return {}\n"
            "@r.get('/items/{id}')\ndef g(id: str):\n    return {}\napp.include_router(r)\n")
    assert check_contract(spec, code).passed
    assert not check_contract(spec, code.replace("@ app.post('/items')", "@app.put('/items')")).passed


def test_own_mutation_score_counts_bugs_seeded_into_the_models_own_app():
    from svaga_platform.app.experiments.grid import own_mutation_score

    app = ("from fastapi import FastAPI, HTTPException\napp = FastAPI()\n"
           "@app.get('/check/{n}')\ndef check(n: int):\n    if n > 10:\n        raise HTTPException(422)\n    return {'ok': True}\n")
    tests = ("from fastapi.testclient import TestClient\nfrom app import app\nc = TestClient(app)\n"
             "def test_small():\n    assert c.get('/check/3').status_code == 200\n"
             "def test_big():\n    assert c.get('/check/11').status_code == 422\n")
    r = own_mutation_score(app, tests)
    assert r["tests_passing_on_own_app"] == 2 and r["mutants"] >= 2 and r["killed"] >= 1


def test_results_api_serves_a_grid_and_blocks_paths_outside_it(tmp_path, monkeypatch):
    monkeypatch.setenv("SVAGA_SCRIPTED_LLM", "1")
    from fastapi.testclient import TestClient

    import svaga_platform.app.results_api as api
    from svaga_platform.app.experiments.grid import run_one
    from svaga_platform.app.main import app

    grid = tmp_path / "grid"
    run_one("m2", "crud_contact_directory", 1, grid / "g1", recall=False)
    monkeypatch.setattr(api, "GRID_DIR", grid)
    c = TestClient(app)
    assert [g["name"] for g in c.get("/api/v1/grid").json()] == ["g1"]
    assert len(c.get("/api/v1/grid/g1").json()["runs"]) == 1
    cell = c.get("/api/v1/grid/g1/compare", params={"task": "crud_contact_directory", "repeat": 1}).json()
    assert "behavior_spec.json" in cell["models"]["m2"]["files"]
    assert c.get("/api/v1/grid/g1/compare", params={"task": "../../x"}).status_code == 400
    assert c.get("/api/v1/grid/g1/charts/..%2F..%2Fsummary.json").status_code in (400, 404)
