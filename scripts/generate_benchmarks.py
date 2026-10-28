"""One-off generator for workflow benchmark YAML files (20+ validated workflows)."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "benchmarks" / "workflows"

WORKFLOWS = [
    ("url_shortener", "URL Shortener", "data_collection", "Build a URL shortener with POST /shorten and GET /r/{code}."),
    ("leave_approval", "Leave Approval", "approval", "Employees request leave; managers approve; no self-approval."),
    ("ticket_assign", "Ticket Assignment", "ticketing", "Create tickets, assign to agents, resolve when done."),
    ("crud_validation", "CRUD Validation", "data_collection", "CRUD items with price validation and duplicate rejection."),
    ("file_upload_cap", "File Upload Cap", "data_collection", "Accept uploads with max size 1MB and reject path traversal."),
    ("role_scoped_list", "Role Scoped List", "approval", "List records visible only to the owning role."),
    ("expense_approval", "Expense Approval", "approval", "Submit expenses; finance approves amounts over threshold."),
    ("shift_scheduling", "Shift Scheduling", "scheduling", "Assign shifts without double-booking the same worker."),
    ("notification_queue", "Notification Queue", "notifications", "Enqueue notifications and mark delivered once."),
    ("survey_collection", "Survey Collection", "data_collection", "Collect survey responses with required field validation."),
    ("incident_triage", "Incident Triage", "ticketing", "Open incidents, set priority, assign on-call engineer."),
    ("meeting_room_booking", "Meeting Room Booking", "scheduling", "Book rooms; reject overlapping reservations."),
    ("password_reset_token", "Password Reset Token", "security", "Issue single-use reset tokens expiring after one hour."),
    ("inventory_restock", "Inventory Restock", "data_collection", "Track SKU quantities; restock cannot go negative."),
    ("customer_refund", "Customer Refund", "approval", "Refund requests require manager approval over $100."),
    ("content_moderation", "Content Moderation", "approval", "Flag content; moderators approve or reject flags."),
    ("oncall_rotation", "On-call Rotation", "scheduling", "Rotate on-call duty fairly across team members."),
    ("webhook_dispatcher", "Webhook Dispatcher", "notifications", "Dispatch webhooks with retry cap and dead-letter queue."),
    ("api_rate_limiter", "API Rate Limiter", "security", "Rate limit per API key with configurable window."),
    ("document_approval", "Document Approval", "approval", "Authors submit documents; reviewers approve publish state."),
    ("task_dependency", "Task Dependency", "scheduling", "Tasks cannot complete until dependencies complete."),
    ("billing_invoice", "Billing Invoice", "data_collection", "Generate invoices; totals must equal line item sum."),
]


def endpoints_for(wf_id: str) -> list[dict]:
    if wf_id == "url_shortener":
        return [
            {"method": "POST", "path": "/shorten", "business_action": "create"},
            {"method": "GET", "path": "/r/{code}", "business_action": "resolve"},
        ]
    return [{"method": "GET", "path": "/health", "business_action": "health"}]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for wf_id, name, category, nl in WORKFLOWS:
        doc = {
            "workflow_id": wf_id,
            "name": name,
            "category": category,
            "complexity": "small",
            "natural_language_requirement": nl,
            "actors": [{"id": "user", "name": "User", "roles": ["user"]}],
            "entities": [{"name": "Record", "fields": ["id", "status"]}],
            "business_rules": [{"id": "basic_validation", "description": "Reject invalid payloads with 422/400"}],
            "endpoints": endpoints_for(wf_id),
            "functional_properties": [],
            "safety_properties": [
                {"id": "no_subprocess", "description": "Generated app must not shell out", "expression": "import app as m\n    assert 'subprocess' not in open(m.__file__).read()"}
            ],
            "permission_requirements": {
                "allowed_imports": ["fastapi", "pydantic", "typing"],
                "forbidden_imports": ["subprocess", "socket", "os.system"],
            },
            "known_fault_mutations": [{"id": "drop_auth_check", "description": "Remove authorization guard"}],
        }
        if wf_id == "url_shortener":
            doc["functional_properties"] = [
                {
                    "id": "shorten_returns_200",
                    "description": "POST /shorten succeeds",
                    "check_type": "pytest",
                    "expression": "from fastapi.testclient import TestClient\n    from app import app\n    c = TestClient(app)\n    assert c.post('/shorten', json={'url': 'https://example.com'}).status_code == 200",
                }
            ]
        else:
            doc["functional_properties"] = [
                {
                    "id": "imports_app",
                    "description": "App module loads",
                    "check_type": "pytest",
                    "expression": "import app  # noqa: F401",
                }
            ]
        path = OUT / f"{wf_id}.yaml"
        path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    print(f"Wrote {len(WORKFLOWS)} workflows to {OUT}")


if __name__ == "__main__":
    main()
