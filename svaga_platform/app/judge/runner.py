"""Run a candidate app in an isolated subprocess and execute a task's hidden checks against it over HTTP.

Isolation today (Day 2): separate process, fresh temporary folder, minimal environment with no API keys, loopback
only, hard timeouts. Docker isolation (no network, dropped capabilities) is layered on later without changing
this interface.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

from shared.benchmarks.private_loader import load_private_task
from shared.paths import SVAGA_ROOT

TEMPLATE = Path(__file__).with_name("conftest_template.py")
SAFE_ENV_KEYS = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "LANG", "PYTHONIOENCODING")


@dataclass
class CheckOutcome:
    id: str
    kind: str
    passed: bool
    detail: str = ""


@dataclass
class JudgeResult:
    task_id: str
    passed: bool
    started: bool
    checks: list[CheckOutcome] = field(default_factory=list)
    error: str = ""
    seconds: float = 0.0
    app_log_tail: str = ""

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["passed_count"] = self.passed_count
        data["total"] = len(self.checks)
        return data


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _minimal_env(extra: dict[str, str]) -> dict[str, str]:
    env = {k: os.environ[k] for k in SAFE_ENV_KEYS if k in os.environ}
    env.update(extra)
    return env


def _wait_until_up(url: str, proc: subprocess.Popen, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        try:
            httpx.get(url + "/openapi.json", timeout=1.0)
            return True
        except httpx.HTTPError:
            time.sleep(0.2)
    return False


def _stop(proc: subprocess.Popen, log_path: Path | None = None) -> str:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    try:
        out = log_path.read_text(encoding="utf-8", errors="replace") if log_path else ""
    except Exception:  # pragma: no cover
        out = ""
    return (out or "")[-2000:]


def _parse_junit(xml_path: Path) -> dict[str, tuple[bool, str]]:
    """Map base test name -> (all cases passed, first failure message). Parametrized cases fold into one check."""
    results: dict[str, tuple[bool, str]] = {}
    if not xml_path.exists():
        return results
    for case in ET.parse(xml_path).getroot().iter("testcase"):
        base = case.get("name", "").split("[")[0]
        failure = case.find("failure") if case.find("failure") is not None else case.find("error")
        skipped = case.find("skipped") is not None
        ok = failure is None and not skipped
        message = "" if ok else ((failure.get("message") if failure is not None else "skipped") or "")[:300]
        prev_ok, prev_msg = results.get(base, (True, ""))
        results[base] = (prev_ok and ok, prev_msg or message)
    return results


def judge_candidate(
    task_id: str,
    app_code: str,
    *,
    startup_timeout: float = 30.0,
    checks_timeout: float = 180.0,
    private_dir: Path | None = None,
) -> JudgeResult:
    private = load_private_task(task_id, private_dir)
    started_at = time.monotonic()
    work = Path(tempfile.mkdtemp(prefix=f"svaga_judge_{task_id}_"))
    app_dir, checks_dir = work / "app", work / "checks"
    app_dir.mkdir()
    checks_dir.mkdir()
    (app_dir / "app.py").write_text(app_code, encoding="utf-8")
    shutil.copy(private.checks_file, checks_dir / "test_hidden.py")
    shutil.copy(TEMPLATE, checks_dir / "conftest.py")

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    # Log to a file, not a pipe: nothing reads a pipe while the checks run, so an app that logs a traceback per
    # request (any 500) fills the OS pipe buffer, blocks on its own write and hangs every remaining check.
    app_log = work / "app.log"
    app_log_file = open(app_log, "wb")
    app_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=app_dir,
        env=_minimal_env({"PYTHONPATH": str(app_dir), "PYTHONDONTWRITEBYTECODE": "1"}),
        stdout=app_log_file,
        stderr=subprocess.STDOUT,
    )
    result = JudgeResult(task_id=task_id, passed=False, started=False)
    try:
        if not _wait_until_up(base_url, app_proc, startup_timeout):
            result.error = "candidate app did not start"
            result.checks = [CheckOutcome(c["id"], c["kind"], False, "app did not start") for c in private.hidden_checks]
            return result
        result.started = True
        junit = work / "junit.xml"
        env = _minimal_env({
            "PYTHONPATH": str(SVAGA_ROOT),
            "SVAGA_JUDGE_BASE_URL": base_url,
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        try:
            subprocess.run(
                [sys.executable, "-m", "pytest", str(checks_dir), "-q", "-p", "no:cacheprovider", "-p", "no:schemathesis",
                 f"--junitxml={junit}", "-o", "junit_family=xunit2", "--rootdir", str(checks_dir)],
                cwd=checks_dir, env=env, capture_output=True, text=True, timeout=checks_timeout,
            )
        except subprocess.TimeoutExpired:
            result.error = f"hidden checks exceeded {checks_timeout:.0f}s"
        outcomes = _parse_junit(junit)
        for check in private.hidden_checks:
            ok, message = outcomes.get(check["id"], (False, "check did not run"))
            result.checks.append(CheckOutcome(check["id"], check["kind"], ok, message))
        undeclared = sorted(set(outcomes) - {c["id"] for c in private.hidden_checks})
        if undeclared:
            result.error = (result.error + "; " if result.error else "") + f"undeclared checks in file: {undeclared}"
        result.passed = bool(result.checks) and all(c.passed for c in result.checks) and not result.error
        return result
    finally:
        result.app_log_tail = _stop(app_proc, app_log)
        app_log_file.close()
        result.seconds = round(time.monotonic() - started_at, 2)
        shutil.rmtree(work, ignore_errors=True)
