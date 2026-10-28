from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


class PolicyDocument(BaseModel):
    allowed_imports: list[str] = Field(default_factory=lambda: ["fastapi", "pydantic", "typing"])
    forbidden_imports: list[str] = Field(
        default_factory=lambda: ["os.system", "subprocess", "socket", "requests"]
    )
    allowed_file_roots: list[str] = Field(default_factory=lambda: ["/tmp", "."])
    max_upload_bytes: int | None = None


@dataclass
class PolicyCheckResult:
    passed: bool
    violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "violations": self.violations}


def check_policy_static(app_code: str, policy: PolicyDocument) -> PolicyCheckResult:
    violations: list[str] = []
    try:
        tree = ast.parse(app_code)
    except SyntaxError as exc:
        return PolicyCheckResult(passed=False, violations=[f"syntax error: {exc}"])

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                chain = _attr_chain(node.func)
                if chain in policy.forbidden_imports or chain.startswith("subprocess"):
                    violations.append(f"forbidden call: {chain}")
            elif isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "__import__"}:
                violations.append(f"forbidden builtin: {node.func.id}")

    for forbidden in policy.forbidden_imports:
        root = forbidden.split(".")[0]
        if root in imports:
            violations.append(f"forbidden import module: {root}")

    return PolicyCheckResult(passed=len(violations) == 0, violations=violations)


def _attr_chain(node: ast.Attribute) -> str:
    parts: list[str] = []
    cur: ast.AST = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))
