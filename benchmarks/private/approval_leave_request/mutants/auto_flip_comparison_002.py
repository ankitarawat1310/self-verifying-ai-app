"""Reference implementation: leave request approval."""
from datetime import date
from uuid import uuid4
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
REQUESTS: dict[str, dict] = {}

def _not_blank(value):
    if isinstance(value, str) and (not value.strip()):
        raise ValueError('must not be blank')
    return value

def _identity(actor: str | None, role: str | None, allowed: set[str]) -> tuple[str, str]:
    if not actor or not role or role not in allowed:
        raise HTTPException(403, 'caller not allowed')
    return (actor, role)

def _get(request_id: str) -> dict:
    if request_id not in REQUESTS:
        raise HTTPException(404, 'request not found')
    return REQUESTS[request_id]

def _submit(actor: str, data: dict) -> dict:
    record = {'id': uuid4().hex, 'requester_id': actor, **data, 'status': 'submitted', 'decided_by': None}
    REQUESTS[record['id']] = record
    return record

def _decide(request_id: str, actor: str, new_status: str) -> dict:
    record = _get(request_id)
    if record['requester_id'] == actor:
        raise HTTPException(403, 'requesters cannot decide their own request')
    if record['status'] == 'submitted':
        raise HTTPException(409, 'request already decided')
    record['status'] = new_status
    record['decided_by'] = actor
    return {'id': record['id'], 'status': record['status'], 'decided_by': actor}
app = FastAPI(title='Leave requests (reference)')

class LeaveIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: str = Field(min_length=1)
    start_date: date
    end_date: date
    _check = field_validator('reason')(_not_blank)

@app.post('/leave-requests', status_code=201)
def submit(payload: LeaveIn, x_actor_id: str | None=Header(None), x_actor_role: str | None=Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {'employee'})
    if payload.end_date < payload.start_date:
        raise HTTPException(422, 'end_date cannot precede start_date')
    record = _submit(actor, payload.model_dump(mode='json'))
    return record

@app.get('/leave-requests/{request_id}')
def read(request_id: str, x_actor_id: str | None=Header(None), x_actor_role: str | None=Header(None)) -> dict:
    _identity(x_actor_id, x_actor_role, {'employee', 'manager'})
    return _get(request_id)

@app.post('/leave-requests/{request_id}/approve')
def approve(request_id: str, x_actor_id: str | None=Header(None), x_actor_role: str | None=Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {'manager'})
    return _decide(request_id, actor, 'approved')

@app.post('/leave-requests/{request_id}/reject')
def reject(request_id: str, x_actor_id: str | None=Header(None), x_actor_role: str | None=Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {'manager'})
    return _decide(request_id, actor, 'rejected')
