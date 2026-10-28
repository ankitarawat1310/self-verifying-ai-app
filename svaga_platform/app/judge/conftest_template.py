"""Copied as conftest.py next to a task's hidden checks when the judge runs them.

Fixtures available to every hidden check:
  client  httpx.Client pointed at the running candidate app
  mock    programmable mock service (connector tasks); reset before every check
  uid     function returning a short unique string, so each check creates its own data
  as_actor(actor_id, role)  headers for header-based identity
"""
from __future__ import annotations

import os
import uuid

import httpx
import pytest

from svaga_platform.app.judge.mock_server import start_mock_server


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ["SVAGA_JUDGE_BASE_URL"]


@pytest.fixture(scope="session")
def _mock_session():
    service, server = start_mock_server(int(os.environ.get("SVAGA_JUDGE_MOCK_PORT", "18765")))
    try:
        yield service
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def mock(_mock_session):
    _mock_session.reset()
    yield _mock_session
    _mock_session.reset()


@pytest.fixture
def client(base_url: str):
    with httpx.Client(base_url=base_url, timeout=float(os.environ.get("SVAGA_JUDGE_REQUEST_TIMEOUT", "15"))) as c:
        yield c


@pytest.fixture
def uid():
    return lambda prefix="x": f"{prefix}{uuid.uuid4().hex[:8]}"


def as_actor(actor_id: str, role: str) -> dict[str, str]:
    return {"x-actor-id": actor_id, "x-actor-role": role}


@pytest.fixture
def actor():
    return as_actor


def at_time(iso: str) -> dict[str, str]:
    """Test-clock header for tasks whose interface declares clock.header = x-clock-now."""
    return {"x-clock-now": iso}


@pytest.fixture
def clock():
    return at_time
