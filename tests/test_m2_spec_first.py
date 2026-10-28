"""M2 spec-first: spec shape, checker, model checker, spec-derived tests, and the pipeline order."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from shared.budget.tracker import BudgetProfile, BudgetTracker
from shared.llm.provider import ScriptedLLMProvider
from svaga_platform.app.spec_first.author import author_spec, normalize, synth_system
from svaga_platform.app.spec_first.behavior_spec import BehaviorSpec, Rule, StateMachine, Transition, skeleton_from_interface
from svaga_platform.app.spec_first.spec_check import check_spec, model_check, validate_spec
from svaga_platform.app.spec_first.spec_tests import build_cases, generate_spec_tests

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "benchmarks" / "public"
PRIVATE = ROOT / "benchmarks" / "private"
FIXTURES = Path(__file__).parent / "fixtures" / "m2_specs"
DEV_TASKS = ["approval_expense_request", "crud_contact_directory", "crud_profile_mass_assignment", "room_booking",
             "webhook_dispatcher"]


def iface(task_id: str) -> dict:
    return yaml.safe_load((PUBLIC / task_id / "task.yaml").read_text(encoding="utf-8"))["interface"]


def fixture_spec(task_id: str) -> BehaviorSpec:
    return BehaviorSpec.model_validate_json((FIXTURES / f"{task_id}.json").read_text(encoding="utf-8"))


def run_tests(src: str, app_code: str, tmp_path: Path) -> subprocess.CompletedProcess:
    (tmp_path / "app.py").write_text(app_code, encoding="utf-8")
    (tmp_path / "test_app.py").write_text(src, encoding="utf-8")
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:warnings", "test_app.py"],
                          cwd=tmp_path, capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("task_dir", sorted(p.name for p in PUBLIC.iterdir()))
def test_skeleton_covers_every_route_and_passes_checks(task_dir):
    i = iface(task_dir)
    spec = skeleton_from_interface(task_dir, i)
    assert len(spec.operations) == len(i["routes"])
    assert check_spec(spec, i).ok


def test_fixture_specs_pass_checks():
    for task in ("approval_leave_request", "ticket_lifecycle"):
        report = check_spec(fixture_spec(task), iface(task))
        assert report.ok, report.errors


def _leave() -> BehaviorSpec:
    return fixture_spec("approval_leave_request")


def test_model_checker_finds_terminal_state_with_a_way_out():
    spec = _leave()
    spec.operations[2].transitions.append(spec.operations[2].transitions[0].model_copy(update={"from_state": "rejected"}))
    report = model_check(spec)
    assert any("terminal state 'rejected' has a way out" in e for e in report.errors)
    assert report.traces and report.traces[0]["property"] == "terminal_closed"


def test_model_checker_finds_unreachable_state_and_dead_end():
    spec = _leave()
    spec.state_machines[0].states.append("escalated")
    spec.state_machines[0].terminal = ["approved"]
    errors = " | ".join(model_check(spec).errors)
    assert "state 'escalated' is unreachable" in errors
    assert "non-terminal state 'rejected' is a dead end" in errors


def test_model_checker_finds_nondeterminism_and_unfireable_transition():
    spec = _leave()
    approve = spec.operations[2]
    approve.transitions.append(approve.transitions[0].model_copy(update={"to_state": "rejected"}))
    approve.rules.append(approve.rules[0].model_copy(update={"kind": "owner_only"}))
    errors = " | ".join(model_check(spec).errors)
    assert "not deterministic" in errors
    assert "can never fire" in errors


def test_validator_flags_unknown_route_state_and_field():
    spec = _leave()
    spec.operations.append(spec.operations[0].model_copy(update={"route": "POST /admin"}))
    spec.operations[2].transitions[0].to_state = "done"
    spec.operations[0].rules[0].fields = ["start_date", "created_at"]
    errors = " | ".join(validate_spec(spec, iface("approval_leave_request")).errors)
    assert "POST /admin is not a route" in errors
    assert "state 'done' is not in" in errors
    assert "not request fields" in errors


def test_normalize_pins_routes_and_roles_to_the_interface():
    i = iface("approval_leave_request")
    skeleton = skeleton_from_interface("approval_leave_request", i)
    raw = _leave().model_dump()
    raw["operations"][2]["roles"] = ["manager", "employee"]  # LLM widened who may approve
    raw["operations"].append({"route": "DELETE /leave-requests/{request_id}", "kind": "delete"})
    del raw["operations"][1]  # LLM forgot the read route
    spec, notes = normalize(raw, skeleton)
    assert spec is not None
    assert {o.route for o in spec.operations} == {o.route for o in skeleton.operations}
    assert spec.op("POST /leave-requests/{request_id}/approve").roles == ["manager"]
    assert any("dropped operation DELETE" in n for n in notes) and any("added missing" in n for n in notes)
    assert "subprocess" in spec.policy.forbidden_imports


class SequenceLLM(ScriptedLLMProvider):
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def complete_json(self, system, user, *, budget=None, **kwargs):
        self.prompts.append((system, user))
        return self.replies.pop(0)


def test_author_gets_one_fix_round_then_falls_back():
    i = iface("approval_leave_request")
    bad = _leave().model_dump()
    bad["state_machines"][0]["initial"] = "draft"
    good = _leave().model_dump()
    llm = SequenceLLM([bad, good])
    spec, meta = author_spec(llm, "approval_leave_request", "req", i)
    assert meta["source"] == "llm" and meta["attempts"] == 2
    assert "initial state 'draft'" in llm.prompts[1][1]  # the checker's error went back to the model
    assert spec.state_machines[0].initial == "submitted"

    spec, meta = author_spec(SequenceLLM([bad, "not json"]), "approval_leave_request", "req", i)
    assert meta["source"] == "skeleton_fallback" and spec.state_machines == []


def test_synth_prompt_shares_generator_rules_but_not_test_rules():
    text = synth_system()
    assert 'extra="forbid"' in text and "FROZEN BehaviorSpec" in text
    assert "Test independence" not in text and "test_code" not in text


@pytest.mark.parametrize("task", ["approval_leave_request", "ticket_lifecycle"])
def test_spec_tests_pass_on_reference_app(task, tmp_path):
    src, summary = generate_spec_tests(fixture_spec(task), iface(task))
    assert summary["by_kind"].get("transition", 0) >= 2
    proc = run_tests(src, (PRIVATE / task / "reference" / "app.py").read_text(encoding="utf-8"), tmp_path)
    assert proc.returncode == 0, proc.stdout[-2000:]


@pytest.mark.parametrize("task", sorted(p.name for p in PUBLIC.iterdir()))
def test_skeleton_spec_tests_pass_on_every_reference_app(task, tmp_path):
    """No false alarms: tests built from the interface alone must pass on all 20 correct apps."""
    src, _ = generate_spec_tests(skeleton_from_interface(task, iface(task)), iface(task))
    proc = run_tests(src, (PRIVATE / task / "reference" / "app.py").read_text(encoding="utf-8"), tmp_path)
    assert proc.returncode == 0, proc.stdout[-2000:]


def test_spec_tests_catch_self_approval(tmp_path):
    ref = (PRIVATE / "approval_leave_request" / "reference" / "app.py").read_text(encoding="utf-8")
    buggy = ref.replace('if record["requester_id"] == actor:', "if False:")
    assert buggy != ref
    src, _ = generate_spec_tests(_leave(), iface("approval_leave_request"))
    proc = run_tests(src, buggy, tmp_path)
    assert proc.returncode != 0
    assert "actor_rule" in proc.stdout


def test_cases_are_skipped_not_faked_when_body_cannot_be_built():
    task = "billing_invoice"
    cases, skipped = build_cases(skeleton_from_interface(task, iface(task)), iface(task))
    assert any("cannot be built" in s for s in skipped)
    assert not any(c["kind"] == "create_ok" and c["route"] == "POST /invoices" for c in cases)


def test_m2_pipeline_freezes_spec_before_code(monkeypatch):
    monkeypatch.setenv("SVAGA_SCRIPTED_LLM", "1")
    import svaga_platform.app.pipelines.m2_spec_first as m2
    from shared.benchmarks.task_package import find_benchmark

    calls = []

    class Recorder(ScriptedLLMProvider):
        def complete_json(self, system, user, *, budget=None, **kwargs):
            calls.append((system, user))
            return super().complete_json(system, user, budget=budget)

    monkeypatch.setattr(m2, "get_llm_provider", lambda: Recorder())
    bench = find_benchmark("approval_leave_request")
    result = m2.M2SpecFirstPipeline().run(bench, budget=BudgetTracker(profile=BudgetProfile(max_llm_calls=20)))
    files = result.artifacts.to_files()
    spec_hash = result.metadata["behavior_spec_hash"]
    assert "BehaviorSpec author" in calls[0][0]
    assert "FROZEN BehaviorSpec" in calls[-1][0] and spec_hash in calls[-1][1]
    assert hashlib.sha256(BehaviorSpec.model_validate_json(files["behavior_spec.json"]).canonical_json().encode()).hexdigest() == spec_hash
    assert spec_hash in files["test_app.py"]
    assert result.metadata["spec_source"] == "llm"
    assert result.decision in ("ACCEPT", "REJECT")
    json.dumps(result.to_dict(), default=str)


# --- fixes from the first qwen probe (Sep 25) ---------------------------------------------------------------

def test_normalize_drops_rules_that_cannot_apply_and_pins_status_codes():
    """qwen wrote field_order on two strings and owner_only on an API with no identity headers, with status 422."""
    task = "crud_profile_mass_assignment"
    i = iface(task)
    raw = skeleton_from_interface(task, i).model_dump()
    create, update = raw["operations"][0], raw["operations"][3]
    create["rules"] = [{"kind": "unique", "fields": ["username"], "error_status": 422},
                       {"kind": "field_order", "fields": ["username", "display_name"], "op": ">=", "error_status": 422}]
    update["rules"] = [{"kind": "owner_only", "fields": ["id"], "error_status": 422}]
    spec, notes = normalize(raw, skeleton_from_interface(task, i), i)
    assert [(r.kind, r.error_status) for r in spec.operations[0].rules] == [("unique", 409)]
    assert spec.operations[3].rules == []
    assert any("two dates, two datetimes or two numbers" in n for n in notes)
    assert any("no identity headers" in n for n in notes)
    assert check_spec(spec, i).ok


def test_create_outcomes_may_branch_but_actions_may_not():
    """webhook_dispatcher: the create call itself ends in delivered or dead_lettered, depending on the service."""
    task = "webhook_dispatcher"
    i = iface(task)
    spec = skeleton_from_interface(task, i)
    create = spec.operations[0]
    assert create.kind == "create"
    create.transitions = [Transition(from_state="pending", to_state="delivered"),
                          Transition(from_state="pending", to_state="dead_lettered")]
    spec.state_machines = [StateMachine(entity=create.entity, initial="pending",
                                        states=["pending", "delivered", "dead_lettered"],
                                        terminal=["delivered", "dead_lettered"])]
    report = model_check(spec)
    assert report.ok, report.errors
    cases, _ = build_cases(spec, i)
    assert not any(c["kind"] in ("transition", "wrong_state") for c in cases)


def test_owner_rule_on_a_delete_route_is_tested_and_catches_the_bug(tmp_path):
    task = "room_booking"
    i = iface(task)
    spec = skeleton_from_interface(task, i)
    delete = spec.op("DELETE /bookings/{booking_id}")
    delete.rules = [Rule(kind="owner_only", fields=["booked_by"], error_status=403)]
    assert check_spec(spec, i).ok
    src, summary = generate_spec_tests(spec, i)
    assert summary["by_kind"].get("actor_rule") == 1
    ref = (PRIVATE / task / "reference" / "app.py").read_text(encoding="utf-8")
    assert run_tests(src, ref, tmp_path).returncode == 0
    buggy_dir = tmp_path / "buggy"
    buggy_dir.mkdir()
    import re

    buggy = re.sub(r"if [^\n]*booked_by[^\n]*!=[^\n]*:", "if False:", ref, count=1)
    assert buggy != ref, "reference owner check not found; update this test"
    proc = run_tests(src, buggy, buggy_dir)
    assert proc.returncode != 0 and "actor_rule" in proc.stdout


# --- fixes from the second qwen probe (Sep 25, run 20260925_080741) --------------------------------------------

def test_qwen_expense_spec_with_a_create_step_passes_on_the_reference(tmp_path):
    """qwen's own spec: initial 'draft', create moves draft -> submitted, then manager approve/reject, not_self."""
    task = "approval_expense_request"
    i = iface(task)
    raw = json.loads((FIXTURES / "approval_expense_request.qwen.json").read_text(encoding="utf-8"))
    spec, notes = normalize(raw, skeleton_from_interface(task, i), i)
    assert any("cannot apply to create" in n for n in notes)  # not_self on the create route is meaningless
    assert check_spec(spec, i).ok
    src, summary = generate_spec_tests(spec, i)
    assert summary["by_kind"]["transition"] == 2 and summary["by_kind"]["actor_rule"] == 2
    ids = json.loads(src.split("IDS = ", 1)[1].split("\n", 1)[0])
    assert not any("from draft" in x for x in ids)  # 'draft' is never visible to a client
    proc = run_tests(src, (PRIVATE / task / "reference" / "app.py").read_text(encoding="utf-8"), tmp_path)
    assert proc.returncode == 0, proc.stdout[-2000:]


def test_reversed_start_end_rule_goes_back_to_the_model():
    """qwen wrote field_order [start_at, end_at] with '>' (start after end); the tests built from it broke create."""
    task = "room_booking"
    i = iface(task)
    spec = skeleton_from_interface(task, i)
    spec.operations[0].rules = [Rule(kind="field_order", fields=["start_at", "end_at"], op=">", error_status=422)]
    errors = validate_spec(spec, i).errors
    assert any("puts the end before the start" in e for e in errors)
    spec.operations[0].rules[0].op = "<"
    assert validate_spec(spec, i).ok


def test_unreachable_states_with_no_action_routes_get_a_create_hint():
    task = "webhook_dispatcher"
    i = iface(task)
    spec = skeleton_from_interface(task, i)
    spec.state_machines = [StateMachine(entity=spec.operations[0].entity, initial="pending",
                                        states=["pending", "delivered"], terminal=["delivered"])]
    errors = " ".join(model_check(spec).errors)
    assert "put those moves on the create operation" in errors


def test_list_routes_are_bare_arrays_in_the_prompt_and_the_spec_tests(tmp_path):
    """Smoke run Sep 26: qwen's profile app wrapped the list in {"profiles": [...]}, M2 accepted it, the judge failed it."""
    from shared.benchmarks.task_package import load_public_task, render_interface_text

    task = "crud_profile_mass_assignment"
    assert "a JSON array (a bare list" in render_interface_text(load_public_task(PUBLIC / task))
    src, summary = generate_spec_tests(skeleton_from_interface(task, iface(task)), iface(task))
    assert summary["by_kind"]["list_shape"] == 1
    ref = (PRIVATE / task / "reference" / "app.py").read_text(encoding="utf-8")
    wrapped = ref.replace("def list_profiles() -> list[dict]:", "def list_profiles():").replace(
        "return list(PROFILES.values())", 'return {"profiles": list(PROFILES.values())}')
    if wrapped == ref:
        pytest.skip("reference list return not found")
    assert run_tests(src, wrapped, tmp_path).returncode != 0
