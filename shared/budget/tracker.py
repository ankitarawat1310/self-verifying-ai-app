from __future__ import annotations

import time
from dataclasses import dataclass, field


class BudgetExceeded(Exception):
    pass


@dataclass
class BudgetProfile:
    max_llm_calls: int = 20
    max_tokens: int = 80_000
    max_verification_seconds: float = 120.0
    max_repair_rounds: int = 3


@dataclass
class BudgetTracker:
    profile: BudgetProfile = field(default_factory=BudgetProfile)
    llm_calls: int = 0
    tokens_used: int = 0
    verification_seconds: float = 0.0
    repair_rounds: int = 0
    _verify_start: float | None = None

    def record_llm(self, tokens: int = 0) -> None:
        self.llm_calls += 1
        self.tokens_used += tokens
        if self.llm_calls > self.profile.max_llm_calls:
            raise BudgetExceeded("LLM call budget exceeded")
        if self.tokens_used > self.profile.max_tokens:
            raise BudgetExceeded("Token budget exceeded")

    def begin_verification(self) -> None:
        self._verify_start = time.monotonic()

    def end_verification(self) -> None:
        if self._verify_start is None:
            return
        self.verification_seconds += time.monotonic() - self._verify_start
        self._verify_start = None
        if self.verification_seconds > self.profile.max_verification_seconds:
            raise BudgetExceeded("Verification time budget exceeded")

    def record_repair_round(self) -> None:
        self.repair_rounds += 1
        if self.repair_rounds > self.profile.max_repair_rounds:
            raise BudgetExceeded("Repair round budget exceeded")

    def to_dict(self) -> dict:
        return {
            "llm_calls": self.llm_calls,
            "tokens_used": self.tokens_used,
            "verification_seconds": round(self.verification_seconds, 3),
            "repair_rounds": self.repair_rounds,
            "profile": {
                "max_llm_calls": self.profile.max_llm_calls,
                "max_tokens": self.profile.max_tokens,
                "max_verification_seconds": self.profile.max_verification_seconds,
                "max_repair_rounds": self.profile.max_repair_rounds,
            },
        }
