from __future__ import annotations

from svaga_platform.app.pipelines.base import Pipeline
from svaga_platform.app.pipelines.m0_plain import M0PlainPipeline
from svaga_platform.app.pipelines.m1_rag import M1RagPipeline
from svaga_platform.app.pipelines.m2_spec_first import M2SpecFirstPipeline
from svaga_platform.app.pipelines.m3_invariants import M3InvariantsPipeline
from svaga_platform.app.pipelines.m4_cegr import M4CegrPipeline

PIPELINES: dict[str, Pipeline] = {
    "m0": M0PlainPipeline(),
    "m1": M1RagPipeline(),
    "m2": M2SpecFirstPipeline(),
    "m3": M3InvariantsPipeline(),
    "m4": M4CegrPipeline(),
}


def get_pipeline(name: str) -> Pipeline:
    key = name.lower().replace("_rag", "").replace("_spec_first", "").replace("_invariants", "").replace("_cegr", "").replace("_plain", "")
    if key not in PIPELINES:
        raise KeyError(f"Unknown pipeline: {name}")
    return PIPELINES[key]
