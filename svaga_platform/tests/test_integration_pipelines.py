from shared.benchmarks.loader import load_benchmark
from shared.budget.tracker import BudgetProfile, BudgetTracker
from shared.paths import BENCHMARKS_DIR

from svaga_platform.app.pipelines.registry import get_pipeline


def test_m1_url_shortener_fake_llm():
    benchmark = load_benchmark(BENCHMARKS_DIR / "url_shortener.yaml")
    budget = BudgetTracker(profile=BudgetProfile(max_llm_calls=5, max_verification_seconds=180))
    result = get_pipeline("m1").run(benchmark, budget=budget)
    assert result.artifacts.app_code
    assert result.verification["verifiers"]


def test_m2_spec_first_produces_spec():
    benchmark = load_benchmark(BENCHMARKS_DIR / "url_shortener.yaml")
    budget = BudgetTracker(profile=BudgetProfile(max_llm_calls=10, max_verification_seconds=180))
    result = get_pipeline("m2").run(benchmark, budget=budget)
    assert result.artifacts.spec_dict()["workflow_id"]
