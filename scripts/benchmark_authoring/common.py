"""Helpers to write v1 task packages (public + private) into the SVAGA 3.0 benchmark folder."""
import os, secrets
from pathlib import Path
import yaml

ROOT = Path(os.environ.get("SVAGA3") or Path(__file__).resolve().parents[2])
STATUS = {"validation_error": 422, "unknown_body_field": 422, "forbidden": 403, "not_found": 404, "conflict": 409}

def w(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))

class Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True
def _str(dumper, data):
    if "\n" in data or len(data) > 90:
        return dumper.represent_scalar("tag:yaml.org,2002:str", " ".join(data.split()), style=">")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)
Dumper.add_representer(str, _str)

def write_task(*, task_id, title, category, source, prompt, interface, private, checks, reference, notes=""):
    if (ROOT / "benchmarks/private" / task_id / "REVIEW.md").exists() and not os.environ.get("SVAGA_FORCE_REGENERATE"):
        # A reviewed task's files are now the source of truth; edit them directly (see manual_review.md).
        print("skipped (manually reviewed)", task_id)
        return
    pub = {"schema_version": "1.0", "task_id": task_id, "title": title, "category": category,
           "source": source, "prompt": " ".join(prompt.split()), "interface": interface}
    w(ROOT / "benchmarks/public" / task_id / "task.yaml", yaml.dump(pub, Dumper=Dumper, sort_keys=False, width=110))
    priv_path = ROOT / "benchmarks/private" / task_id / "private.yaml"
    canary = None
    if priv_path.exists():
        canary = yaml.safe_load(priv_path.read_text(encoding="utf-8")).get("canary")
    canary = canary or f"SVAGA-PRIVATE-CANARY-{task_id}-{secrets.token_hex(6)}"
    priv = {"schema_version": "1.0", "task_id": task_id, "canary": canary, "split": "unassigned", **private,
            "hidden_checks": checks_meta(checks)}
    if notes:
        priv["notes"] = notes
    w(priv_path, yaml.dump(priv, Dumper=Dumper, sort_keys=False, width=110))
    w(ROOT / "benchmarks/private" / task_id / "checks/test_hidden.py", checks.strip() + "\n")
    w(ROOT / "benchmarks/private" / task_id / "reference/app.py", reference.strip() + "\n")
    print("wrote", task_id)

import ast
def checks_meta(source: str):
    """Hidden check list derived from the checks file: each test's docstring starts with [functional] or [safety]."""
    out = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            doc = (ast.get_docstring(node) or "").strip()
            assert doc.startswith("[functional]") or doc.startswith("[safety]"), node.name
            kind = "functional" if doc.startswith("[functional]") else "safety"
            out.append({"id": node.name, "kind": kind, "description": doc.split("]", 1)[1].strip()})
    return out
