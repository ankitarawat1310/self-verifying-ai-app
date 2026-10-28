"""Re-export shared sandbox for Model 1 API."""

from shared.sandbox.pytest_runner import SandboxResult, execute_pytest_sandbox

__all__ = ["execute_pytest_sandbox", "SandboxResult"]
