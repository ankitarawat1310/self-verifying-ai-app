"""Seeded-bug generator: deterministic, one change per mutant, and kept mutants are real (caught) bugs."""
from __future__ import annotations

import ast
import json

from shared.benchmarks.private_loader import load_all_private_tasks
from svaga_platform.app.judge.mutation import OPERATORS, generate_candidates, sample_candidates

SAMPLE = '''
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI()
LIMIT = 5


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n: int = Field(ge=0)


@app.post("/x", status_code=201)
def create(payload: In) -> dict:
    if payload.n > LIMIT and True:
        raise HTTPException(409, "too big")
    return {"n": payload.n}
'''


def test_every_operator_finds_a_site_and_each_mutant_differs_by_one_change():
    candidates = generate_candidates(SAMPLE)
    assert {m.operator for m in candidates} == {name for name, _, _ in OPERATORS}
    original = ast.unparse(ast.parse(SAMPLE))
    for m in candidates:
        assert m.source.strip() != original
        ast.parse(m.source)


def test_sampling_is_deterministic_and_operator_balanced():
    candidates = generate_candidates(SAMPLE)
    a = [m.mutant_id for m in sample_candidates(candidates, 6, seed=7)]
    b = [m.mutant_id for m in sample_candidates(generate_candidates(SAMPLE), 6, seed=7)]
    assert a == b
    assert len({m.split("_0")[0] for m in a}) == 6


def test_every_task_has_three_security_bugs_caught_by_their_intended_check():
    for task in load_all_private_tasks():
        manifest = json.loads((task.mutants_dir / "security_manifest.json").read_text(encoding="utf-8"))
        assert manifest["total"] >= 3, task.task_id
        for entry in manifest["mutants"]:
            assert entry["valid"] and entry["expected_hit"], (task.task_id, entry["id"])
            assert (task.mutants_dir / f"{entry['id']}.py").exists(), entry["id"]


def test_every_task_has_at_least_five_kept_mutants_that_were_caught():
    for task in load_all_private_tasks():
        manifest = json.loads((task.mutants_dir / "manifest.json").read_text(encoding="utf-8"))
        kept = [e for e in manifest["mutants"] if e["outcome"] == "killed"]
        assert len(kept) >= 5, task.task_id
        for entry in kept:
            assert entry["killed_by"], entry["id"]
            assert (task.mutants_dir / f"{entry['id']}.py").exists(), entry["id"]
