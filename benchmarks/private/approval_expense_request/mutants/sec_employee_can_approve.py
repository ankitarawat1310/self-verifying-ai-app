"""Reference implementation: expense request approval."""

from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

REQUESTS: dict[str, dict] = {}


def _not_blank(value):
    if isinstance(value, str) and not value.strip():
        raise ValueError("must not be blank")
    return value


def _identity(actor: str | None, role: str | None, allowed: set[str]) -> tuple[str, str]:
    if not actor or not role or role not in allowed:
        raise HTTPException(403, "caller not allowed")
    return actor, role


def _get(request_id: str) -> dict:
    if request_id not in REQUESTS:
        raise HTTPException(404, "request not found")
    return REQUESTS[request_id]


def _submit(actor: str, data: dict) -> dict:
    record = {"id": uuid4().hex, "requester_id": actor, **data, "status": "submitted", "decided_by": None}
    REQUESTS[record["id"]] = record
    return record


def _decide(request_id: str, actor: str, new_status: str) -> dict:
    record = _get(request_id)
    if record["requester_id"] == actor:
        raise HTTPException(403, "requesters cannot decide their own request")
    if record["status"] != "submitted":
        raise HTTPException(409, "request already decided")
    record["status"] = new_status
    record["decided_by"] = actor
    return {"id": record["id"], "status": record["status"], "decided_by": actor}


app = FastAPI(title="Expense requests (reference)")


class ExpenseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: float = Field(gt=0)
    description: str = Field(min_length=1)
    _check = field_validator("description")(_not_blank)


@app.post("/expense-requests", status_code=201)
def submit(payload: ExpenseIn, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {"employee"})
    return _submit(actor, payload.model_dump())


@app.get("/expense-requests/{request_id}")
def read(request_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    _identity(x_actor_id, x_actor_role, {"employee", "manager"})
    return _get(request_id)


@app.post("/expense-requests/{request_id}/approve")
def approve(request_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {"manager", "employee"})
    return _decide(request_id, actor, "approved")


@app.post("/expense-requests/{request_id}/reject")
def reject(request_id: str, x_actor_id: str | None = Header(None), x_actor_role: str | None = Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {"manager"})
    return _decide(request_id, actor, "rejected")
