from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from shared.benchmarks.loader import BenchmarkWorkflow
from shared.budget.tracker import BudgetProfile, BudgetTracker

from svaga_platform.app.artifacts import PipelineArtifacts


@dataclass
class PipelineResult:
    pipeline: str
    workflow_id: str
    artifacts: PipelineArtifacts
    verification: dict[str, Any]
    decision: str
    budget: dict[str, Any]
    counterexamples: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline": self.pipeline,
            "workflow_id": self.workflow_id,
            "decision": self.decision,
            "artifacts": self.artifacts.to_files(),
            "verification": self.verification,
            "budget": self.budget,
            "counterexamples": self.counterexamples,
            "metadata": self.metadata,
            "spec_hash": self.artifacts.spec_hash,
        }


class Pipeline(ABC):
    name: str

    @abstractmethod
    def run(
        self,
        benchmark: BenchmarkWorkflow,
        *,
        budget: BudgetTracker,
        model: str | None = None,
    ) -> PipelineResult:
        raise NotImplementedError
