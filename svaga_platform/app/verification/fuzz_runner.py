from __future__ import annotations

import random
import re
import sys
import time
import types
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FuzzRunResult:
    passed: bool
    attempts: int = 0
    failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "attempts": self.attempts, "failures": self.failures}


def run_api_fuzz(app_code: str, spec: dict[str, Any], *, max_seconds: float = 5.0, max_attempts: int = 30) -> FuzzRunResult:
    """Lightweight route fuzz using TestClient when FastAPI app is present."""
    if "FastAPI" not in app_code:
        return FuzzRunResult(passed=True, attempts=0, failures=[])

    # This module uses `from __future__ import annotations`, and exec() of a string inherits that flag
    # unless told otherwise, which turned every annotation in the generated app into a string. Those were
    # then resolved against a bare-dict namespace (classes get __module__ == "builtins"), so every route
    # with a request-body model failed with "TypeAdapter[...] is not fully defined". Compile the app on its
    # own terms (dont_inherit) and run it as a registered module so its types resolve like a real import.
    module_name = f"_svaga_fuzz_{uuid.uuid4().hex}"
    module = types.ModuleType(module_name)
    sys.modules[module_name] = module
    try:
        return _fuzz_module(module, app_code, spec, max_seconds=max_seconds, max_attempts=max_attempts)
    finally:
        sys.modules.pop(module_name, None)


def _fuzz_module(module: types.ModuleType, app_code: str, spec: dict[str, Any], *, max_seconds: float, max_attempts: int) -> FuzzRunResult:
    namespace = module.__dict__
    try:
        exec(compile(app_code, "<generated app>", "exec", dont_inherit=True), namespace)
    except Exception as exc:
        return FuzzRunResult(passed=False, attempts=0, failures=[f"exec failed: {exc}"])

    app = namespace.get("app")
    if app is None:
        return FuzzRunResult(passed=True, attempts=0)

    from fastapi.testclient import TestClient

    client = TestClient(app)
    endpoints = spec.get("endpoints") or []
    random.seed(0)
    deadline = time.monotonic() + max_seconds
    failures: list[str] = []
    attempts = 0
    while attempts < max_attempts and time.monotonic() < deadline:
        attempts += 1
        if not endpoints:
            break
        ep = random.choice(endpoints)
        path = ep.get("path", "/")
        method = ep.get("method", "GET").upper()
        path = re.sub(r"\{[^}]+\}", str(random.randint(1, 50)), path)
        try:
            if method == "GET":
                res = client.get(path)
            elif method == "POST":
                res = client.post(path, json={"url": "fuzz", "name": "x", "id": 1})
            else:
                res = client.request(method, path)
            if res.status_code >= 500:
                failures.append(f"{method} {path} -> {res.status_code}")
        except Exception as exc:
            failures.append(f"{method} {path} exception: {exc}")

    return FuzzRunResult(passed=len(failures) == 0, attempts=attempts, failures=failures[:5])
