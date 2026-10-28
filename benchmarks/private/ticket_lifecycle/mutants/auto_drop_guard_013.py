"""Reference implementation: support ticket lifecycle."""
from uuid import uuid4
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

def _not_blank(value):
    if isinstance(value, str) and (not value.strip()):
        raise ValueError('must not be blank')
    return value

def _identity(actor, role, allowed):
    if not actor or not role or role not in allowed:
        raise HTTPException(403, 'caller not allowed')
    return (actor, role)
app = FastAPI(title='Ticket lifecycle (reference)')
TICKETS: dict[str, dict] = {}
ALL_ROLES = {'customer', 'agent', 'manager'}

class TicketIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    _check = field_validator('title', 'description')(_not_blank)

def _get(ticket_id: str) -> dict:
    if ticket_id not in TICKETS:
        raise HTTPException(404, 'ticket not found')
    return TICKETS[ticket_id]

def _move(ticket: dict, expected: str, new_status: str) -> dict:
    if ticket['status'] != expected:
        raise HTTPException(409, f'ticket must be {expected}')
    ticket['status'] = new_status
    return ticket

@app.post('/tickets', status_code=201)
def open_ticket(payload: TicketIn, x_actor_id: str | None=Header(None), x_actor_role: str | None=Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {'customer'})
    ticket = {'id': uuid4().hex, 'requester_id': actor, **payload.model_dump(), 'status': 'open'}
    TICKETS[ticket['id']] = ticket
    return ticket

@app.get('/tickets/{ticket_id}')
def read(ticket_id: str, x_actor_id: str | None=Header(None), x_actor_role: str | None=Header(None)) -> dict:
    _identity(x_actor_id, x_actor_role, ALL_ROLES)
    return _get(ticket_id)

@app.post('/tickets/{ticket_id}/start')
def start(ticket_id: str, x_actor_id: str | None=Header(None), x_actor_role: str | None=Header(None)) -> dict:
    _identity(x_actor_id, x_actor_role, {'agent'})
    return _move(_get(ticket_id), 'open', 'in_progress')

@app.post('/tickets/{ticket_id}/resolve')
def resolve(ticket_id: str, x_actor_id: str | None=Header(None), x_actor_role: str | None=Header(None)) -> dict:
    _identity(x_actor_id, x_actor_role, {'agent'})
    return _move(_get(ticket_id), 'in_progress', 'resolved')

@app.post('/tickets/{ticket_id}/close')
def close(ticket_id: str, x_actor_id: str | None=Header(None), x_actor_role: str | None=Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {'customer'})
    ticket = _get(ticket_id)
    if False:
        raise HTTPException(403, 'only the requester can close')
    return _move(ticket, 'resolved', 'closed')

@app.post('/tickets/{ticket_id}/reopen')
def reopen(ticket_id: str, x_actor_id: str | None=Header(None), x_actor_role: str | None=Header(None)) -> dict:
    actor, role = _identity(x_actor_id, x_actor_role, ALL_ROLES)
    ticket = _get(ticket_id)
    if ticket['status'] == 'closed':
        if role != 'manager':
            raise HTTPException(403, 'only a manager can reopen a closed ticket')
        return _move(ticket, 'closed', 'in_progress')
    if role == 'manager' or (role == 'customer' and ticket['requester_id'] != actor):
        raise HTTPException(403, 'not allowed to reopen')
    return _move(ticket, 'resolved', 'in_progress')
