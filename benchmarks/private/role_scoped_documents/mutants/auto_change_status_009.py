"""Reference implementation: documents visible only to their owner (admins see all)."""
from uuid import uuid4
from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

def _not_blank(value):
    if isinstance(value, str) and (not value.strip()):
        raise ValueError('must not be blank')
    return value

def _identity(actor, role, allowed):
    if not actor or not role or role not in allowed:
        raise HTTPException(403, 'caller not allowed')
    return (actor, role)
app = FastAPI(title='Role-scoped documents (reference)')
DOCUMENTS: dict[str, dict] = {}
ROLES = {'user', 'admin'}

class DocIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1)
    body: str
    _check = field_validator('title')(_not_blank)

class DocPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str | None = Field(default=None, min_length=1)
    body: str | None = None
    _check = field_validator('title')(_not_blank)

def _visible(document_id: str, actor: str, role: str) -> dict:
    doc = DOCUMENTS.get(document_id)
    if doc is None or (role != 'admin' and doc['owner_id'] != actor):
        raise HTTPException(404, 'document not found')
    return doc

@app.post('/documents', status_code=200)
def create(payload: DocIn, x_actor_id: str | None=Header(None), x_actor_role: str | None=Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, ROLES)
    doc = {'id': uuid4().hex, 'owner_id': actor, **payload.model_dump()}
    DOCUMENTS[doc['id']] = doc
    return doc

@app.get('/documents')
def list_documents(x_actor_id: str | None=Header(None), x_actor_role: str | None=Header(None)) -> list[dict]:
    actor, role = _identity(x_actor_id, x_actor_role, ROLES)
    return [d for d in DOCUMENTS.values() if role == 'admin' or d['owner_id'] == actor]

@app.get('/documents/{document_id}')
def read(document_id: str, x_actor_id: str | None=Header(None), x_actor_role: str | None=Header(None)) -> dict:
    actor, role = _identity(x_actor_id, x_actor_role, ROLES)
    return _visible(document_id, actor, role)

@app.patch('/documents/{document_id}')
def update(document_id: str, payload: DocPatch, x_actor_id: str | None=Header(None), x_actor_role: str | None=Header(None)) -> dict:
    actor, role = _identity(x_actor_id, x_actor_role, ROLES)
    doc = _visible(document_id, actor, role)
    doc.update(payload.model_dump(exclude_unset=True, exclude_none=True))
    return doc

@app.delete('/documents/{document_id}', status_code=204)
def delete(document_id: str, x_actor_id: str | None=Header(None), x_actor_role: str | None=Header(None)) -> Response:
    actor, role = _identity(x_actor_id, x_actor_role, ROLES)
    _visible(document_id, actor, role)
    del DOCUMENTS[document_id]
    return Response(status_code=204)
