import os

import pytest

from shared.benchmarks.loader import load_all_benchmarks
from shared.budget.tracker import BudgetProfile, BudgetTracker
from svaga_platform.app.pipelines.registry import get_pipeline


@pytest.mark.parametrize(
    "workflow_id",
    ["url_shortener", "billing_invoice", "schedule_meeting"],
)
def test_m1_scripted_respects_workflow(workflow_id):
    os.environ["SVAGA_SCRIPTED_LLM"] = "1"
    benchmarks = {b.workflow_id: b for b in load_all_benchmarks()}
    pipeline = get_pipeline("m1")
    result = pipeline.run(
        benchmarks[workflow_id],
        budget=BudgetTracker(profile=BudgetProfile(max_llm_calls=50)),
    )
    app = result.artifacts.app_code
    spec = result.artifacts.spec_dict()
    assert spec.get("workflow_id") == workflow_id
    if workflow_id == "url_shortener":
        assert "/shorten" in app
    else:
        assert "/shorten" not in app
        assert workflow_id in app or spec.get("application_name", "").lower().replace(" ", "_") in app.lower()
