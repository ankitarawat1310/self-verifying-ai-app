"""Reference implementation: user profiles with mass-assignment protection."""
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
app = FastAPI(title='User profiles (reference)')
PROFILES: dict[str, dict] = {}

def _not_blank(value):
    if value is not None and (not value.strip()):
        raise ValueError('must not be blank')
    return value

class ProfileIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    _check = field_validator('username', 'display_name')(_not_blank)

class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str | None = Field(default=None, min_length=1)
    display_name: str | None = Field(default=None, min_length=1)
    _check = field_validator('username', 'display_name')(_not_blank)

def _get(profile_id: str) -> dict:
    if profile_id not in PROFILES:
        raise HTTPException(404, 'profile not found')
    return PROFILES[profile_id]

def _username_taken(username: str, exclude: str | None=None) -> bool:
    return any((p['username'] == username and pid != exclude for pid, p in PROFILES.items()))

@app.post('/profiles', status_code=201)
def create_profile(payload: ProfileIn) -> dict:
    if _username_taken(payload.username):
        raise HTTPException(409, 'username already exists')
    profile = {'id': uuid4().hex, **payload.model_dump()}
    PROFILES[profile['id']] = profile
    return profile

@app.get('/profiles')
def list_profiles() -> list[dict]:
    return list(PROFILES.values())

@app.get('/profiles/{profile_id}')
def read_profile(profile_id: str) -> dict:
    return _get(profile_id)

@app.patch('/profiles/{profile_id}')
def update_profile(profile_id: str, payload: ProfilePatch) -> dict:
    profile = _get(profile_id)
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if 'username' in changes and _username_taken(changes['username'], exclude=profile_id):
        raise HTTPException(400, 'username already exists')
    profile.update(changes)
    return profile

@app.delete('/profiles/{profile_id}', status_code=204)
def delete_profile(profile_id: str) -> Response:
    _get(profile_id)
    del PROFILES[profile_id]
    return Response(status_code=204)
