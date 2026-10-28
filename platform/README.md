# Platform orchestrator

Python package lives in [`../svaga_platform/`](../svaga_platform/) as `svaga_platform` to avoid shadowing the Python stdlib `platform` module when `PYTHONPATH` includes the repo root.

Run: `uvicorn svaga_platform.app.main:app --reload --port 8080`

A mirror of the application package also lives under `platform/app/` for layout parity with the architecture doc; import `svaga_platform` in Python to avoid stdlib shadowing issues.
