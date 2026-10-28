"""Reference implementation: meeting room booking without overlaps."""
from datetime import datetime, timedelta
from typing import Literal
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
app = FastAPI(title='Room booking (reference)')
BOOKINGS: dict[str, dict] = {}
Room = Literal['room-a', 'room-b', 'room-c']
MAX_LENGTH = timedelta(hours=4)

class BookingIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    room_id: Room
    title: str = Field(min_length=1)
    start_at: datetime
    end_at: datetime
    _check = field_validator('title')(_not_blank)

def _out(b: dict) -> dict:
    return {**b, 'start_at': b['start_at'].isoformat(), 'end_at': b['end_at'].isoformat()}

def _get(booking_id: str) -> dict:
    if booking_id not in BOOKINGS:
        raise HTTPException(404, 'booking not found')
    return BOOKINGS[booking_id]

@app.post('/bookings', status_code=201)
def book(payload: BookingIn, x_actor_id: str | None=Header(None), x_actor_role: str | None=Header(None)) -> dict:
    actor, _ = _identity(x_actor_id, x_actor_role, {'employee'})
    if payload.end_at <= payload.start_at:
        raise HTTPException(422, 'end_at must be after start_at')
    if payload.end_at - payload.start_at > MAX_LENGTH:
        raise HTTPException(422, 'bookings last at most 4 hours')
    for other in BOOKINGS.values():
        if other['room_id'] != payload.room_id and payload.start_at < other['end_at'] and (other['start_at'] < payload.end_at):
            raise HTTPException(409, 'room already booked')
    booking = {'id': uuid4().hex, 'booked_by': actor, **payload.model_dump()}
    BOOKINGS[booking['id']] = booking
    return _out(booking)

@app.get('/bookings')
def list_bookings(room_id: Room | None=None, x_actor_id: str | None=Header(None), x_actor_role: str | None=Header(None)) -> list[dict]:
    _identity(x_actor_id, x_actor_role, {'employee'})
    return [_out(b) for b in BOOKINGS.values() if room_id is None or b['room_id'] == room_id]

@app.get('/bookings/{booking_id}')
def read(booking_id: str, x_actor_id: str | None=Header(None), x_actor_role: str | None=Header(None)) -> dict:
    _identity(x_actor_id, x_actor_role, {'employee'})
    return _out(_get(booking_id))

@app.delete('/bookings/{booking_id}', status_code=204)
def cancel(booking_id: str, x_actor_id: str | None=Header(None), x_actor_role: str | None=Header(None)) -> Response:
    actor, _ = _identity(x_actor_id, x_actor_role, {'employee'})
    booking = _get(booking_id)
    if booking['booked_by'] != actor:
        raise HTTPException(403, 'only the booker can cancel')
    del BOOKINGS[booking_id]
    return Response(status_code=204)
