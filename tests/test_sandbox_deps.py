"""The sandbox runs generated apps with the parent's interpreter; check the deps generated apps commonly need."""
from shared.sandbox.pytest_runner import execute_pytest_sandbox

EMAILSTR_APP = '''
from fastapi import FastAPI
from pydantic import BaseModel, EmailStr

app = FastAPI()


class Reset(BaseModel):
    email: EmailStr


@app.post("/reset")
def reset(body: Reset):
    return {"email": body.email}
'''

EMAILSTR_TEST = '''
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_valid_email_accepted():
    assert client.post("/reset", json={"email": "user@example.com"}).status_code == 200


def test_invalid_email_rejected():
    assert client.post("/reset", json={"email": "not-an-email"}).status_code == 422
'''


def test_sandbox_supports_pydantic_emailstr():
    res = execute_pytest_sandbox(EMAILSTR_APP, EMAILSTR_TEST)
    assert res.passed, res.stdout
    assert res.passed_tests == 2


ZONEINFO_APP = '''
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI

app = FastAPI()


@app.get("/now")
def now():
    return {"utc": datetime.now(ZoneInfo("UTC")).isoformat()}
'''

ZONEINFO_TEST = '''
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_utc_zoneinfo_resolves():
    assert client.get("/now").status_code == 200
'''


def test_sandbox_supports_zoneinfo_utc():
    """Windows has no system IANA database; ZoneInfo("UTC") only works when the tzdata package is installed."""
    res = execute_pytest_sandbox(ZONEINFO_APP, ZONEINFO_TEST)
    assert res.passed, res.stdout
    assert res.passed_tests == 1


def test_requirements_txt_lists_tzdata():
    from pathlib import Path

    lines = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8").splitlines()
    assert any(line.split("#")[0].strip().startswith("tzdata") for line in lines)
