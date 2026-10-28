"""Automatic seeded-bug generator for benchmark reference apps (mutation testing).

Each mutant changes exactly one site in the reference app with one of six operators. The judge then classifies it:
  killed    the app starts and at least one hidden check fails  -> a real, detectable bug; kept in the benchmark
  survived  every hidden check still passes                     -> equivalent change or a gap in the checks; reviewed
  crashed   the app does not start                              -> trivially caught; discarded

Kept mutants are the seeded faults behind the property-violation-recall metric.
"""
from __future__ import annotations

import ast
import copy
import random
from dataclasses import dataclass
from typing import Callable

STATUS_SWAP = {400: 422, 401: 403, 403: 404, 404: 403, 409: 400, 422: 400, 423: 401, 500: 502, 502: 500,
               200: 201, 201: 200, 202: 200, 204: 200}
COMPARE_SWAP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Eq: ast.NotEq,
                ast.NotEq: ast.Eq, ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is}
RELAXABLE_KEYWORDS = {"extra", "ge", "gt", "le", "lt", "min_length", "max_length", "pattern"}
NO_NUMBER_MUTATION_CALLS = {"HTTPException", "token_bytes", "token_urlsafe", "token_hex", "pbkdf2_hmac", "Decimal"}
NO_NUMBER_MUTATION_KEYWORDS = {"status_code", "timeout"}


@dataclass
class Mutant:
    mutant_id: str
    operator: str
    lineno: int
    description: str
    source: str


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        f = node.func
        return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
    return ""


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


# Each operator: (name, site finder, applier). Sites are indexes into ast.walk order plus a variant.

def _flip_comparison_sites(tree, parents):
    return [(i, 0) for i, n in enumerate(ast.walk(tree))
            if isinstance(n, ast.Compare) and len(n.ops) == 1 and type(n.ops[0]) in COMPARE_SWAP]


def _flip_comparison_apply(node, _variant):
    old = type(node.ops[0])
    node.ops = [COMPARE_SWAP[old]()]
    return f"comparison {old.__name__} -> {COMPARE_SWAP[old].__name__}"


def _drop_guard_sites(tree, parents):
    return [(i, 0) for i, n in enumerate(ast.walk(tree))
            if isinstance(n, ast.If) and any(isinstance(s, ast.Raise) for s in n.body)]


def _drop_guard_apply(node, _variant):
    before = ast.unparse(node.test)
    node.test = ast.Constant(False)
    return f"guard disabled: if {before[:70]}"


def _status_sites(tree, parents):
    sites = []
    for i, n in enumerate(ast.walk(tree)):
        if _call_name(n) == "HTTPException" and n.args and isinstance(n.args[0], ast.Constant)                 and n.args[0].value in STATUS_SWAP:
            sites.append((i, 0))
        if isinstance(n, ast.keyword) and n.arg == "status_code" and isinstance(n.value, ast.Constant)                 and n.value.value in STATUS_SWAP:
            sites.append((i, 1))
    return sites


def _status_apply(node, variant):
    target = node.args[0] if variant == 0 else node.value
    old = target.value
    target.value = STATUS_SWAP[old]
    return f"status code {old} -> {STATUS_SWAP[old]}"


def _boolean_sites(tree, parents):
    sites = []
    for i, n in enumerate(ast.walk(tree)):
        if isinstance(n, ast.BoolOp):
            sites.append((i, 0))
        elif isinstance(n, ast.Constant) and isinstance(n.value, bool) and not isinstance(parents.get(n), ast.keyword):
            sites.append((i, 1))
    return sites


def _boolean_apply(node, variant):
    if variant == 0:
        old = type(node.op).__name__
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        return f"boolean operator {old} -> {type(node.op).__name__}"
    node.value = not node.value
    return f"constant {not node.value} -> {node.value}"


def _relax_sites(tree, parents):
    sites = []
    for i, n in enumerate(ast.walk(tree)):
        if _call_name(n) in {"Field", "ConfigDict"}:
            for k, kw in enumerate(n.keywords):
                if kw.arg in RELAXABLE_KEYWORDS:
                    sites.append((i, k))
        if isinstance(n, ast.Name) and n.id in {"StrictInt", "EmailStr"}:
            sites.append((i, -1))
    return sites


def _relax_apply(node, variant):
    if variant == -1:
        old = node.id
        node.id = "int" if old == "StrictInt" else "str"
        return f"type {old} -> {node.id}"
    kw = node.keywords.pop(variant)
    return f"validation removed: {kw.arg}={ast.unparse(kw.value)}"


def _number_sites(tree, parents):
    sites = []
    for i, n in enumerate(ast.walk(tree)):
        if not (isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)):
            continue
        p = parents.get(n)
        if isinstance(p, ast.keyword) and p.arg in NO_NUMBER_MUTATION_KEYWORDS:
            continue
        if isinstance(p, ast.Call) and _call_name(p) in NO_NUMBER_MUTATION_CALLS:
            continue
        if isinstance(p, ast.keyword) and _call_name(parents.get(p)) in NO_NUMBER_MUTATION_CALLS:
            continue
        if isinstance(p, ast.Subscript) or isinstance(parents.get(p), ast.Subscript):
            continue
        sites.append((i, 0))
    return sites


def _number_apply(node, _variant):
    old = node.value
    node.value = old + 1
    return f"number {old} -> {node.value}"


OPERATORS: list[tuple[str, Callable, Callable]] = [
    ("flip_comparison", _flip_comparison_sites, _flip_comparison_apply),
    ("drop_guard", _drop_guard_sites, _drop_guard_apply),
    ("change_status", _status_sites, _status_apply),
    ("swap_boolean", _boolean_sites, _boolean_apply),
    ("relax_validation", _relax_sites, _relax_apply),
    ("off_by_one", _number_sites, _number_apply),
]


def generate_candidates(source: str) -> list[Mutant]:
    tree = ast.parse(source)
    parents = _parents(tree)
    out: list[Mutant] = []
    for name, find, apply in OPERATORS:
        for index, variant in find(tree, parents):
            clone = copy.deepcopy(tree)
            node = list(ast.walk(clone))[index]
            description = apply(node, variant)
            mutated = ast.unparse(ast.fix_missing_locations(clone))
            if mutated == ast.unparse(tree):
                continue
            out.append(Mutant(f"{name}_{len(out):03d}", name, getattr(node, "lineno", 0), description, mutated + "\n"))
    return out


def sample_candidates(candidates: list[Mutant], limit: int, seed: int) -> list[Mutant]:
    """Seeded, operator-balanced sample: round-robin over operators so every kind of bug is represented."""
    rng = random.Random(seed)
    by_op: dict[str, list[Mutant]] = {}
    for m in candidates:
        by_op.setdefault(m.operator, []).append(m)
    for items in by_op.values():
        rng.shuffle(items)
    picked: list[Mutant] = []
    while len(picked) < limit and any(by_op.values()):
        for op in sorted(by_op):
            if by_op[op] and len(picked) < limit:
                picked.append(by_op[op].pop())
    return picked
