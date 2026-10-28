from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from shared.schemas.workflow_spec import WorkflowSpecDocument


@dataclass
class ContractCheckResult:
    passed: bool
    missing_paths: list[str] = field(default_factory=list)
    extra_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "missing_paths": self.missing_paths,
            "extra_paths": self.extra_paths,
        }


def _regex_routes(app_code: str) -> set[str]:
    # fallback only; tolerates "@ app.post(" and routers ("@router.get(")
    return {f"{m.upper()} {p}" for m, p in re.findall(
        r'@\s*\w+\s*\.\s*(get|post|put|delete|patch)\(\s*[\'"]([^\'"]+)', app_code, flags=re.IGNORECASE)}


def _live_routes(app_code: str) -> set[str] | None:
    """Routes as FastAPI registered them (method + path), by importing the app like the fuzz runner does.

    A regex over source text missed decorators written as "@ app.post(...)" and routes added through an APIRouter,
    so correct apps failed the contract (smoke run Sep 26: M2 expense passed 14/14 hidden checks and was rejected).
    """
    import sys
    import types
    import uuid

    name = f"_svaga_contract_{uuid.uuid4().hex}"
    module = types.ModuleType(name)
    sys.modules[name] = module
    try:
        exec(compile(app_code, "<generated app>", "exec", dont_inherit=True), module.__dict__)
        app = module.__dict__.get("app")
        if app is None or not hasattr(app, "routes"):
            return None
        out = set()
        for route in app.routes:
            for method in getattr(route, "methods", None) or ():
                if method not in ("HEAD", "OPTIONS"):
                    out.add(f"{method} {route.path}")
        return out
    except Exception:
        return None
    finally:
        sys.modules.pop(name, None)


def _shape(route: str) -> str:
    """Path parameter names do not matter to a client: /items/{item_id} and /items/{id} are the same route."""
    return re.sub(r"\{[^}]*\}", "{}", route)


def check_contract(spec: WorkflowSpecDocument, app_code: str) -> ContractCheckResult:
    declared = {_shape(f"{e.method.upper()} {e.path}") for e in spec.endpoints}
    found = _live_routes(app_code)
    if found is None:
        found = _regex_routes(app_code)
    found = {_shape(r) for r in found}
    missing = sorted(declared - found)
    extra = sorted(found - declared)
    return ContractCheckResult(passed=len(missing) == 0, missing_paths=missing, extra_paths=extra)
