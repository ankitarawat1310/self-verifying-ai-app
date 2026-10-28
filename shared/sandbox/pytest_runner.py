from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SandboxResult:
    passed: bool
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    stdout: str = ""
    stderr: str = ""
    report: dict[str, Any] = field(default_factory=dict)
    workspace: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "report": self.report,
        }


def execute_pytest_sandbox(
    app_code: str,
    test_code: str,
    *,
    extra_files: dict[str, str] | None = None,
    timeout_seconds: int = 30,
) -> SandboxResult:
    """Run pytest in an isolated temp directory with no network in child env."""
    extra_files = extra_files or {}
    with tempfile.TemporaryDirectory(prefix="svaga_sandbox_") as tmp:
        workspace = Path(tmp)
        (workspace / "app.py").write_text(app_code, encoding="utf-8")
        (workspace / "test_app.py").write_text(test_code, encoding="utf-8")
        for name, content in extra_files.items():
            (workspace / name).write_text(content, encoding="utf-8")

        report_path = workspace / "report.json"
        env = os.environ.copy()
        env["NO_NETWORK"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "test_app.py",
            "-p",
            "no:schemathesis",
            "-p",
            "no:hypothesis",
            "--json-report",
            f"--json-report-file={report_path}",
            "-q",
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            return SandboxResult(
                passed=False,
                stdout=exc.stdout or "",
                stderr=(exc.stderr or "") + "\nSandbox timeout exceeded.",
                workspace=str(workspace),
            )

        report: dict[str, Any] = {}
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                report = {}

        summary = report.get("summary", {})
        total = int(summary.get("total", 0))
        passed_count = int(summary.get("passed", 0))
        failed = int(summary.get("failed", 0))

        return SandboxResult(
            passed=proc.returncode == 0 and failed == 0 and total > 0,
            total_tests=total,
            passed_tests=passed_count,
            failed_tests=failed,
            stdout=proc.stdout,
            stderr=proc.stderr,
            report=report,
            workspace=str(workspace),
        )
