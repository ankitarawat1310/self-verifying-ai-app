from shared.benchmarks.loader import load_all_benchmarks


def test_load_all_benchmarks_valid():
    benchmarks = load_all_benchmarks()
    assert len(benchmarks) >= 20
