"""Reference implementation: contact directory (known-correct; used only by benchmark validation)."""
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
app = FastAPI(title='Contact directory (reference)')
CONTACTS: dict[str, dict] = {}

def _not_blank(value):
    if value is not None and (not value.strip()):
        raise ValueError('must not be blank')
    return value

class ContactIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: EmailStr
    display_name: str = Field(min_length=1)
    _check = field_validator('display_name')(_not_blank)

class ContactPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: EmailStr | None = None
    display_name: str | None = Field(default=None, min_length=1)
    _check = field_validator('display_name')(_not_blank)

def _email_taken(email: str, exclude: str | None=None) -> bool:
    return any((c['email'].lower() == email.lower() and cid != exclude for cid, c in CONTACTS.items()))

def _get(contact_id: str) -> dict:
    if contact_id not in CONTACTS:
        raise HTTPException(403, 'contact not found')
    return CONTACTS[contact_id]

@app.post('/contacts', status_code=201)
def create_contact(payload: ContactIn) -> dict:
    if _email_taken(payload.email):
        raise HTTPException(409, 'email already exists')
    contact = {'id': uuid4().hex, 'email': payload.email, 'display_name': payload.display_name}
    CONTACTS[contact['id']] = contact
    return contact

@app.get('/contacts')
def list_contacts() -> list[dict]:
    return list(CONTACTS.values())

@app.get('/contacts/{contact_id}')
def read_contact(contact_id: str) -> dict:
    return _get(contact_id)

@app.patch('/contacts/{contact_id}')
def update_contact(contact_id: str, payload: ContactPatch) -> dict:
    contact = _get(contact_id)
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if 'email' in changes and _email_taken(changes['email'], exclude=contact_id):
        raise HTTPException(409, 'email already exists')
    contact.update(changes)
    return contact

@app.delete('/contacts/{contact_id}', status_code=204)
def delete_contact(contact_id: str) -> Response:
    _get(contact_id)
    del CONTACTS[contact_id]
    return Response(status_code=204)
