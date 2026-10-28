from __future__ import annotations

import io
import json
import uuid
import zipfile
from pathlib import Path
from typing import Any

from shared.generation.deploy_bundle import prepare_artifacts_from_disk
from shared.paths import RESULTS_DIR


def new_run_id() -> str:
    return uuid.uuid4().hex


def run_dir(run_id: str) -> Path:
    path = RESULTS_DIR / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def persist_run(run_id: str, payload: dict[str, Any]) -> Path:
    root = run_dir(run_id)
    (root / "run.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    artifacts = payload.get("artifacts") or {}
    art_dir = root / "artifacts"
    art_dir.mkdir(exist_ok=True)
    for name, content in artifacts.items():
        if isinstance(content, str):
            (art_dir / name).write_text(content, encoding="utf-8")
    provenance = payload.get("provenance")
    if provenance:
        (root / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    verification = payload.get("verification")
    if verification:
        (root / "verification_report.json").write_text(json.dumps(verification, indent=2), encoding="utf-8")
    return root


def load_run(run_id: str) -> dict[str, Any]:
    path = RESULTS_DIR / run_id / "run.json"
    if not path.exists():
        raise FileNotFoundError(run_id)
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_path(run_id: str, filename: str) -> Path:
    return RESULTS_DIR / run_id / "artifacts" / filename


def build_zip(run_id: str) -> bytes:
    root = RESULTS_DIR / run_id
    if not root.exists():
        raise FileNotFoundError(run_id)
    buf = io.BytesIO()
    art = root / "artifacts"
    deploy_files: dict[str, str] = {}
    if art.exists():
        deploy_files = prepare_artifacts_from_disk(art)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in deploy_files.items():
            zf.writestr(name, content)
        for extra in ("run.json", "provenance.json", "verification_report.json"):
            p = root / extra
            if p.exists():
                zf.write(p, arcname=extra)
    return buf.getvalue()
