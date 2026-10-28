"""Reference implementation: single-use, expiring, superseding password reset tokens."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field

def _now(header_value):
    if header_value:
        moment = datetime.fromisoformat(header_value.replace('Z', '+00:00'))
        return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)
app = FastAPI(title='Password reset (reference)')
USERS: dict[str, dict] = {}
TOKENS: dict[str, dict] = {}
OUTBOX: dict[str, str] = {}
TTL = timedelta(minutes=60)

def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)

def _set_password(user: dict, password: str) -> None:
    user['salt'] = secrets.token_bytes(16)
    user['hash'] = _hash(password, user['salt'])

class RegisterIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: EmailStr
    password: str = Field(min_length=8)

class LoginIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str
    password: str

class ResetRequestIn(BaseModel):
    model_config = ConfigDict()
    email: str

class ConfirmIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str
    new_password: str = Field(min_length=8)

@app.post('/users', status_code=201)
def register(payload: RegisterIn) -> dict:
    if payload.email in USERS:
        raise HTTPException(409, 'email already registered')
    user = {'id': uuid4().hex, 'email': payload.email}
    _set_password(user, payload.password)
    USERS[payload.email] = user
    return {'id': user['id'], 'email': user['email']}

@app.post('/login')
def login(payload: LoginIn) -> dict:
    user = USERS.get(payload.email)
    if user is None or not hmac.compare_digest(user['hash'], _hash(payload.password, user['salt'])):
        raise HTTPException(401, 'invalid credentials')
    return {'email': payload.email}

@app.post('/password-resets', status_code=202)
def request_reset(payload: ResetRequestIn, x_clock_now: str | None=Header(None)) -> dict:
    now = _now(x_clock_now)
    if payload.email in USERS:
        for record in TOKENS.values():
            if record['email'] == payload.email:
                record['valid'] = False
        token = secrets.token_urlsafe(24)
        TOKENS[token] = {'email': payload.email, 'expires': now + TTL, 'valid': True}
        OUTBOX[payload.email] = token
    return {'status': 'requested'}

@app.get('/outbox/{email}')
def outbox(email: str) -> dict:
    if email not in OUTBOX:
        raise HTTPException(404, 'no message')
    return {'token': OUTBOX[email]}

@app.post('/password-resets/confirm')
def confirm(payload: ConfirmIn, x_clock_now: str | None=Header(None)) -> dict:
    now = _now(x_clock_now)
    record = TOKENS.get(payload.token)
    if record is None or not record['valid'] or now >= record['expires']:
        raise HTTPException(400, 'invalid or expired token')
    record['valid'] = False
    _set_password(USERS[record['email']], payload.new_password)
    return {'status': 'password_updated'}
