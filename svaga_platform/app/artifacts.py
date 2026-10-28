from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from shared.generation.deploy_bundle import REQUIREMENTS_TXT, build_readme, build_run_ps1
from shared.generation.simple_ui import finalize_generated_app, finalize_generated_tests
from shared.policy.checker import PolicyDocument
from shared.schemas.workflow_spec import WorkflowSpecDocument


@dataclass
class PipelineArtifacts:
    app_code: str
    test_code: str
    workflow_spec: WorkflowSpecDocument | dict[str, Any]
    policy: PolicyDocument
    test_properties_code: str = ""
    spec_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    extra_files: dict[str, str] = field(default_factory=dict)  # e.g. M2's frozen behavior_spec.json

    def __post_init__(self) -> None:
        spec = self.spec_dict()
        self.app_code = finalize_generated_app(self.app_code, spec)
        self.test_code = finalize_generated_tests(self.test_code, spec)
        if not self.spec_hash:
            payload = self.workflow_spec.model_dump(mode="json") if isinstance(self.workflow_spec, WorkflowSpecDocument) else self.workflow_spec
            self.spec_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def spec_dict(self) -> dict[str, Any]:
        if isinstance(self.workflow_spec, WorkflowSpecDocument):
            return self.workflow_spec.to_dict()
        return dict(self.workflow_spec)

    def to_files(self) -> dict[str, str]:
        spec = self.spec_dict()
        files = {
            "app.py": self.app_code,
            "test_app.py": self.test_code,
            "workflow_spec.json": json.dumps(spec, indent=2),
            "policy.json": self.policy.model_dump_json(indent=2),
            "requirements.txt": REQUIREMENTS_TXT,
            "run.ps1": build_run_ps1(),
            "README.md": build_readme(spec),
        }
        if self.test_properties_code:
            files["test_properties.py"] = self.test_properties_code
        files.update(self.extra_files)
        return files
