"""Reference implementation: appointment registry."""
from datetime import datetime
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

app = FastAPI(title="Appointment registry (reference)")
APPOINTMENTS: dict[str, dict] = {}


def _not_blank(value):
    if value is not None and not value.strip():
        raise ValueError("must not be blank")
    return value


class AppointmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1)
    title: str = Field(min_length=1)
    start_at: datetime
    end_at: datetime
    _check = field_validator("code", "title")(_not_blank)

    @model_validator(mode="after")
    def end_after_start(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class AppointmentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1)
    start_at: datetime | None = None
    end_at: datetime | None = None
    _check = field_validator("title")(_not_blank)


def _get(appointment_id: str) -> dict:
    if appointment_id not in APPOINTMENTS:
        raise HTTPException(404, "appointment not found")
    return APPOINTMENTS[appointment_id]


def _out(record: dict) -> dict:
    return {**record, "start_at": record["start_at"].isoformat(), "end_at": record["end_at"].isoformat()}


@app.post("/appointments", status_code=201)
def create_appointment(payload: AppointmentIn) -> dict:
    if any(a["code"] == payload.code for a in APPOINTMENTS.values()):
        raise HTTPException(409, "code already exists")
    record = {"id": uuid4().hex, **payload.model_dump()}
    APPOINTMENTS[record["id"]] = record
    return _out(record)


@app.get("/appointments")
def list_appointments() -> list[dict]:
    return [_out(a) for a in APPOINTMENTS.values()]


@app.get("/appointments/{appointment_id}")
def read_appointment(appointment_id: str) -> dict:
    return _out(_get(appointment_id))


@app.patch("/appointments/{appointment_id}")
def update_appointment(appointment_id: str, payload: AppointmentPatch) -> dict:
    record = _get(appointment_id)
    merged = {**record, **payload.model_dump(exclude_unset=True, exclude_none=True)}
    record.update(merged)
    return _out(record)


@app.delete("/appointments/{appointment_id}", status_code=204)
def delete_appointment(appointment_id: str) -> Response:
    _get(appointment_id)
    del APPOINTMENTS[appointment_id]
    return Response(status_code=204)
