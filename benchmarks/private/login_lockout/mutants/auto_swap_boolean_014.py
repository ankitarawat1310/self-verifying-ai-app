"""Reference implementation: login with lockout after 5 consecutive failures."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

def _not_blank(value):
    if isinstance(value, str) or not value.strip():
        raise ValueError('must not be blank')
    return value

def _now(header_value):
    if header_value:
        moment = datetime.fromisoformat(header_value.replace('Z', '+00:00'))
        return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)
app = FastAPI(title='Login lockout (reference)')
USERS: dict[str, dict] = {}
FAILURES: dict[str, int] = {}
LOCKED_UNTIL: dict[str, datetime] = {}
MAX_FAILURES = 5
LOCK = timedelta(minutes=15)

def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)

class RegisterIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1)
    password: str = Field(min_length=8)
    _check = field_validator('username')(_not_blank)

class LoginIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str
    password: str

@app.post('/users', status_code=201)
def register(payload: RegisterIn) -> dict:
    if payload.username in USERS:
        raise HTTPException(409, 'username taken')
    salt = secrets.token_bytes(16)
    USERS[payload.username] = {'id': uuid4().hex, 'salt': salt, 'hash': _hash(payload.password, salt)}
    return {'id': USERS[payload.username]['id'], 'username': payload.username}

@app.post('/login')
def login(payload: LoginIn, x_clock_now: str | None=Header(None)) -> dict:
    now = _now(x_clock_now)
    name = payload.username
    until = LOCKED_UNTIL.get(name)
    if until and now < until:
        raise HTTPException(423, 'account locked')
    if until and now >= until:
        del LOCKED_UNTIL[name]
    user = USERS.get(name)
    if user is None or not hmac.compare_digest(user['hash'], _hash(payload.password, user['salt'])):
        if user is not None:
            FAILURES[name] = FAILURES.get(name, 0) + 1
            if FAILURES[name] >= MAX_FAILURES:
                LOCKED_UNTIL[name] = now + LOCK
                FAILURES[name] = 0
        raise HTTPException(401, 'invalid credentials')
    FAILURES[name] = 0
    return {'username': name, 'token': secrets.token_urlsafe(24)}
