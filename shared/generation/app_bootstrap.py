"""Ensure generated FastAPI apps expose / and /health for local runs."""

from __future__ import annotations

import ast
import re

_ROOT_ROUTE = '''

@app.get("/")
def _svaga_root():
    return {"status": "ok", "app": "generated", "docs": "/docs", "openapi": "/openapi.json"}
'''

_HEALTH_ROUTE = '''
@app.get("/health")
def _svaga_health():
    return {"status": "ok"}
'''

_ROUTE_METHODS = frozenset({"get", "post", "put", "delete", "patch", "head", "options", "api_route", "route"})
_ADD_ROUTE_METHODS = frozenset({"add_api_route", "add_route"})

# Fallback for code that does not parse: `@app.get("/health"`, `router.add_api_route('/health'`, ...
_ROUTE_RE_TEMPLATE = (
    r"\b\w+\.(?:get|post|put|delete|patch|head|options|api_route|route|add_api_route|add_route)"
    r"\(\s*(?:path\s*=\s*)?(['\"]){path}\1"
)


def _parse(app_code: str) -> ast.Module | None:
    try:
        return ast.parse(app_code)
    except (SyntaxError, ValueError):
        return None


def _first_str_arg(call: ast.Call) -> str | None:
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    for kw in call.keywords:
        if kw.arg == "path" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def defines_route(app_code: str, path: str) -> bool:
    """True if the code registers ``path`` on any FastAPI app/router, however the decorator is written."""
    tree = _parse(app_code)
    if tree is None:
        return re.search(_ROUTE_RE_TEMPLATE.format(path=re.escape(path)), app_code) is not None
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr in _ROUTE_METHODS | _ADD_ROUTE_METHODS and _first_str_arg(node) == path:
            return True
    return False


def _is_fastapi_call(value: ast.expr | None) -> bool:
    if not isinstance(value, ast.Call):
        return False
    func = value.func
    return (isinstance(func, ast.Name) and func.id == "FastAPI") or (
        isinstance(func, ast.Attribute) and func.attr == "FastAPI"
    )


def _app_statement_end_line(tree: ast.Module) -> int | None:
    """1-based last line of the top-level ``app = FastAPI(...)`` statement, however many lines it spans."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and _is_fastapi_call(node.value):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and _is_fastapi_call(node.value):
            targets = [node.target]
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == "app" for t in targets):
            return node.end_lineno
    return None


def _inject_after_app(app_code: str, snippet: str) -> str:
    """Insert ``snippet`` right after the whole ``app = FastAPI(...)`` statement.

    Falls back to appending at the end of the file when the statement cannot be located
    (or the code does not parse), so injection never splits a statement.
    """
    tree = _parse(app_code)
    end_line = _app_statement_end_line(tree) if tree is not None else None
    if end_line is None:
        return app_code + snippet
    lines = app_code.splitlines(keepends=True)
    head, tail = "".join(lines[:end_line]), "".join(lines[end_line:])
    if head and not head.endswith("\n"):
        head += "\n"
    return head + snippet + tail


def ensure_fastapi_health_route(app_code: str) -> str:
    if defines_route(app_code, "/health"):
        return app_code
    return _inject_after_app(app_code, "\n" + _HEALTH_ROUTE)


def ensure_fastapi_welcome_routes(app_code: str) -> str:
    if "FastAPI" not in app_code:
        return app_code
    snippets = []
    if not defines_route(app_code, "/"):
        snippets.append(_ROOT_ROUTE)
    if not defines_route(app_code, "/health"):
        snippets.append(_HEALTH_ROUTE)
    if not snippets:
        return app_code
    return _inject_after_app(app_code, "".join(snippets))
