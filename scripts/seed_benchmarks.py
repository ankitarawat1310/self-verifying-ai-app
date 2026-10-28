"""Generate workflow benchmark YAML files (20+)."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "benchmarks" / "workflows"

URL_PROP = [
    {
        "id": "shorten_returns_200",
        "description": "POST /shorten returns 200",
        "expression": (
            "from fastapi.testclient import TestClient\n"
            "    from app import app\n"
            "    c = TestClient(app)\n"
            "    r = c.post('/shorten', json={'url': 'https://a.com'})\n"
            "    assert r.status_code == 200"
        ),
    }
]

WORKFLOWS = [
    ("url_shortener", "URL Shortener", "data_collection", "Build a URL shortener with POST /shorten and GET /r/{code}.", URL_PROP),
    ("leave_approval", "Leave Approval", "approval", "Leave requests: employee submits, manager approves; no self-approval.", []),
    ("ticket_assign", "Ticket Assign", "ticketing", "Assign tickets to agents; only managers may assign.", []),
    ("ticket_resolve", "Ticket Resolve", "ticketing", "Agents resolve tickets; closed tickets cannot reopen without manager.", []),
    ("crud_validation", "CRUD Validation", "data_collection", "CRUD API with positive price validation on items.", []),
    ("file_upload_cap", "File Upload Cap", "data_collection", "Reject uploads over 1MB.", []),
    ("role_scoped_list", "Role Scoped List", "approval", "List endpoint returns only rows visible to caller role.", []),
    ("schedule_meeting", "Schedule Meeting", "scheduling", "Book meetings without double-booking same room.", []),
    ("notify_on_status", "Status Notifications", "notifications", "Emit notification when ticket status changes.", []),
    ("expense_report", "Expense Report", "approval", "Submit expenses; finance approves amounts over threshold.", []),
    ("inventory_adjust", "Inventory Adjust", "data_collection", "Adjust stock counts; prevent negative inventory.", []),
    ("user_registration", "User Registration", "data_collection", "Register users with unique email constraint.", []),
    ("password_reset", "Password Reset", "security", "Issue reset tokens expiring after 15 minutes.", []),
    ("audit_log", "Audit Log", "security", "Append-only audit entries for privileged actions.", []),
    ("rate_limit_login", "Rate Limit Login", "security", "Lock account after 5 failed login attempts.", []),
    ("csv_import", "CSV Import", "data_collection", "Parse CSV with required headers id,name,amount.", []),
    ("api_key_gate", "API Key Gate", "security", "Protect /protected-resource with X-API-Key header.", []),
    ("duplicate_reject", "Duplicate Reject", "data_collection", "Reject duplicate primary keys on create.", []),
    ("state_machine_task", "Task State Machine", "ticketing", "Tasks flow open->in_progress->done.", []),
    ("escalation_policy", "Escalation Policy", "ticketing", "Escalate unassigned tickets after SLA breach.", []),
    ("shift_swap", "Shift Swap", "scheduling", "Employees request shift swaps; manager approves.", []),
    ("announcement_broadcast", "Announcements", "notifications", "Admins broadcast announcements to all users.", []),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for wf_id, name, category, nl, props in WORKFLOWS:
        endpoints = [
            {"method": "POST", "path": "/shorten", "business_action": "create_short_link", "allowed_roles": ["user"]},
            {"method": "GET", "path": "/r/{code}", "business_action": "resolve", "allowed_roles": ["user"]},
        ] if wf_id == "url_shortener" else [
            {"method": "GET", "path": "/health", "business_action": "health", "allowed_roles": ["user"]}
        ]
        doc = {
            "workflow_id": wf_id,
            "name": name,
            "category": category,
            "complexity": "small",
            "natural_language_requirement": nl,
            "endpoints": endpoints,
            "actors": [{"id": "user", "name": "User"}, {"id": "admin", "name": "Admin"}],
            "entities": [{"name": "Record", "fields": [{"name": "id", "type": "string"}]}],
            "business_rules": [{"id": f"{wf_id}_rule", "description": nl}],
            "functional_properties": props,
            "safety_properties": [
                {
                    "id": "no_subprocess",
                    "description": "Generated app must not spawn subprocesses",
                    "predicate": "no_subprocess",
                }
            ],
            "permission_requirements": {
                "allowed_capabilities": ["fastapi", "pydantic"],
                "forbidden_imports": ["subprocess", "socket"],
                "allowed_imports": ["fastapi", "pydantic", "typing"],
            },
            "known_fault_mutations": [],
        }
        path = OUT / f"{wf_id}.yaml"
        path.write_text(yaml.dump(doc, sort_keys=False), encoding="utf-8")
    print(f"Wrote {len(WORKFLOWS)} benchmarks to {OUT}")


if __name__ == "__main__":
    main()
