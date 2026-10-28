"""Independent judge and benchmark v1 validity.

For every v1 task: the reference app passes 100% of hidden checks and an empty app passes none. A hand-made bug
(self-approval allowed) must be caught by exactly the check written for it.
"""
from __future__ import annotations

import pytest

from shared.benchmarks.private_loader import load_all_private_tasks
from svaga_platform.app.judge import judge_candidate

TASKS = load_all_private_tasks()
STUB = "from fastapi import FastAPI\napp = FastAPI()\n"


def test_benchmark_v1_has_twelve_ported_tasks_with_enough_checks():
    assert len(TASKS) >= 12
    for task in TASKS:
        assert len(task.hidden_checks) >= 10, task.task_id
        assert any(c["kind"] == "safety" for c in task.hidden_checks), task.task_id
        assert task.reference_app.exists() and task.checks_file.exists(), task.task_id


@pytest.mark.parametrize("task", TASKS, ids=[t.task_id for t in TASKS])
def test_reference_passes_every_hidden_check(task):
    result = judge_candidate(task.task_id, task.reference_app.read_text(encoding="utf-8"))
    assert result.started, result.app_log_tail
    failed = [(c.id, c.detail) for c in result.checks if not c.passed]
    assert result.passed and not failed, (failed, result.error)


@pytest.mark.parametrize("task", TASKS, ids=[t.task_id for t in TASKS])
def test_empty_app_passes_no_hidden_check(task):
    result = judge_candidate(task.task_id, STUB)
    assert result.started
    assert [c.id for c in result.checks if c.passed] == []


def test_seeded_self_approval_bug_is_caught_by_its_check():
    task = next(t for t in TASKS if t.task_id == "approval_expense_request")
    code = task.reference_app.read_text(encoding="utf-8").replace("\r\n", "\n")
    guard = '    if record["requester_id"] == actor:\n        raise HTTPException(403, "requesters cannot decide their own request")\n'
    assert guard in code
    result = judge_candidate(task.task_id, code.replace(guard, ""))
    assert result.started
    assert [c.id for c in result.checks if not c.passed] == ["test_requester_cannot_self_approve_even_as_manager"]


def test_app_that_does_not_start_fails_every_check():
    task = TASKS[0]
    result = judge_candidate(task.task_id, "this is not python", startup_timeout=10)
    assert not result.started and not result.passed
    assert result.passed_count == 0 and len(result.checks) == len(task.hidden_checks)


NOISY_APP = STUB + """
import sys

@app.middleware("http")
async def noisy(request, call_next):
    sys.stderr.write("x" * 200_000 + "\\n")
    sys.stderr.flush()
    return await call_next(request)
"""


def test_app_that_logs_heavily_does_not_hang_the_judge():
    """A candidate that logs a traceback per request must be scored, not deadlock on a full stdout pipe."""
    result = judge_candidate("room_booking", NOISY_APP, checks_timeout=120)
    assert result.started
    assert "exceeded" not in (result.error or ""), result.error
    assert [c.id for c in result.checks if c.passed] == []
    assert result.seconds < 120
