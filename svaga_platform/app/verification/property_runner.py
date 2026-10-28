from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from typing import Any

from shared.benchmarks.loader import BenchmarkWorkflow
from shared.sandbox.pytest_runner import execute_pytest_sandbox


@dataclass
class PropertyRunResult:
    passed: bool
    results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "results": self.results}


def run_benchmark_properties(app_code: str, test_code: str, benchmark: BenchmarkWorkflow) -> PropertyRunResult:
    checks: list[str] = []
    for prop in benchmark.functional_properties + benchmark.safety_properties:
        expr = prop.get("expression")
        if not expr:
            continue
        body = textwrap.indent(textwrap.dedent(str(expr)).strip(), "    ")
        checks.append(f"def test_property_{prop['id']}():\n{body}\n")
    if not checks:
        return PropertyRunResult(passed=True, results=[{"note": "no executable properties"}])

    property_tests = "\n".join(checks)
    sandbox = execute_pytest_sandbox(
        app_code,
        "def test_benchmark_properties_placeholder(): pass",
        extra_files={"test_benchmark_props.py": property_tests},
    )
    return PropertyRunResult(
        passed=sandbox.passed,
        results=[
            {
                "sandbox": sandbox.to_dict(),
                "property_count": len(checks),
            }
        ],
    )
