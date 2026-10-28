"""Reference implementation: webhook dispatch with at most 3 attempts and dead-lettering."""
from typing import Any, Literal
from uuid import uuid4
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict
RECEIVER_URL = 'http://127.0.0.1:18765/hooks/receive'
MAX_ATTEMPTS = 3
app = FastAPI(title='Webhook dispatcher (reference)')
EVENTS: dict[str, dict] = {}

class EventIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['order.created', 'order.cancelled']
    payload: dict[str, Any]

def _deliver(event: dict) -> None:
    body = {'event_id': event['id'], 'type': event['type'], 'payload': event['payload']}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        event['attempts'] = attempt
        try:
            reply = httpx.post(RECEIVER_URL, json=body, timeout=5.0)
            if 200 <= reply.status_code < 300:
                event['status'] = 'delivered'
                return
        except httpx.HTTPError:
            pass
    event['status'] = 'dead_lettered'

@app.post('/events', status_code=200)
def accept(payload: EventIn) -> dict:
    event = {'id': uuid4().hex, 'type': payload.type, 'payload': payload.payload, 'status': 'pending', 'attempts': 0}
    EVENTS[event['id']] = event
    _deliver(event)
    return event

@app.get('/events/{event_id}')
def read(event_id: str) -> dict:
    if event_id not in EVENTS:
        raise HTTPException(404, 'event not found')
    return EVENTS[event_id]

@app.get('/dead-letters')
def dead_letters() -> list[dict]:
    return [e for e in EVENTS.values() if e['status'] == 'dead_lettered']
