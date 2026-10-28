import pytest

from shared.budget.tracker import BudgetExceeded, BudgetProfile, BudgetTracker
from shared.policy.checker import PolicyDocument, check_policy_static


def test_policy_forbidden_subprocess():
    code = "import subprocess\nsubprocess.call(['ls'])"
    result = check_policy_static(code, PolicyDocument())
    assert not result.passed
    assert result.violations


def test_budget_llm_cap():
    tracker = BudgetTracker(profile=BudgetProfile(max_llm_calls=1))
    tracker.record_llm()
    with pytest.raises(BudgetExceeded):
        tracker.record_llm()
