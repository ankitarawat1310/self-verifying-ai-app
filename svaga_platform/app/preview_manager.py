from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from svaga_platform.app.run_store import artifact_path

_PREVIEW: dict[str, "PreviewSession"] = {}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@dataclass
class PreviewSession:
    run_id: str
    port: int
    process: subprocess.Popen[Any]
    workspace: Path

    @property
    def docs_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/docs"

    @property
    def app_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/ui"

    @property
    def health_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/health"


def start_preview(run_id: str, *, timeout_seconds: float = 15.0) -> dict[str, Any]:
    stop_preview(run_id)
    app_file = artifact_path(run_id, "app.py")
    if not app_file.exists():
        raise FileNotFoundError("app.py not in run artifacts")

    workspace = app_file.parent
    # Serve the app through a small wrapper that adds the SVAGA web UI when the app lacks it (runs made before the
    # UI existed). The wrapper only adds /ui and / if missing, so apps that already have them are unchanged.
    import json as _json

    from shared.generation.simple_ui import ui_block

    spec_file = workspace / "workflow_spec.json"
    try:
        spec = _json.loads(spec_file.read_text(encoding="utf-8")) if spec_file.exists() else {}
    except ValueError:
        spec = {}
    (workspace / "_svaga_preview.py").write_text("from app import app\n" + ui_block(spec), encoding="utf-8")
    port = _free_port()
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    # Log to a file, not a pipe: nothing reads a pipe while the preview runs, so a chatty app would block on write.
    log = open(workspace / "_svaga_preview.log", "wb")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "_svaga_preview:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(workspace),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    session = PreviewSession(run_id=run_id, port=port, process=proc, workspace=workspace)
    _PREVIEW[run_id] = session

    deadline = time.monotonic() + timeout_seconds
    ready = False
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            log.flush()
            err = (workspace / "_svaga_preview.log").read_text(encoding="utf-8", errors="replace")[-500:]
            raise RuntimeError(f"preview process exited: {err[:500]}")
        try:
            r = httpx.get(session.health_url, timeout=1.0)
            if r.status_code == 200:
                ready = True
                break
        except Exception:
            pass
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/openapi.json", timeout=1.0)
            if r.status_code == 200:
                ready = True
                break
        except Exception:
            pass
        time.sleep(0.25)

    if not ready:
        stop_preview(run_id)
        raise RuntimeError("preview did not become ready in time")

    return {"run_id": run_id, "port": port, "docs_url": session.docs_url, "app_url": session.app_url, "ready": True}


def stop_preview(run_id: str) -> dict[str, Any]:
    session = _PREVIEW.pop(run_id, None)
    if not session:
        return {"run_id": run_id, "stopped": False}
    session.process.terminate()
    try:
        session.process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        session.process.kill()
    return {"run_id": run_id, "stopped": True}
