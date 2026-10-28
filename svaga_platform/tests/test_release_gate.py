from svaga_platform.app.release_gate import evaluate_release_gate
from svaga_platform.app.verification.orchestrator import VerificationReport


def test_release_gate_reject_on_failed_verification():
    report = VerificationReport(passed=False, counterexamples=[{"property_id": "x", "message": "fail"}])
    gate = evaluate_release_gate(report, spec_hash="a", frozen_spec_hash="a", policy_passed=True)
    assert gate.decision == "REJECT"


def test_release_gate_accept_when_clean():
    report = VerificationReport(passed=True, verifiers=[{"name": "pytest", "passed": True}])
    gate = evaluate_release_gate(report, spec_hash="a", frozen_spec_hash="a", policy_passed=True)
    assert gate.decision == "ACCEPT"
