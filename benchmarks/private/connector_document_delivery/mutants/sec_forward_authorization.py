"""Reference implementation: document delivery via a fixed mocked connector."""
from uuid import uuid4

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

CONNECTOR_URL = "http://127.0.0.1:18765/documents/deliver"
ALLOWED_STATUS = {"accepted", "queued"}
app = FastAPI(title="Document delivery (reference)")
DELIVERIES: list[dict] = []


class DeliveryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str = Field(min_length=1)
    recipient: str = Field(min_length=1)

    @field_validator("document_id", "recipient")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("must not be blank")
        return value


@app.post("/deliveries", status_code=201)
def deliver(payload: DeliveryIn, authorization: str | None = Header(None)) -> dict:
    try:
        # A fresh request with no caller headers: nothing from the incoming request is forwarded except the body.
        reply = httpx.post(CONNECTOR_URL, json=payload.model_dump(), timeout=5.0, headers={"Authorization": authorization} if authorization else None)
        reply.raise_for_status()
        data = reply.json()
        delivery_id, status = data["delivery_id"], data["status"]
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(502, "delivery connector failed") from error
    if not isinstance(delivery_id, str) or not delivery_id.strip() or status not in ALLOWED_STATUS:
        raise HTTPException(502, "invalid connector reply")
    result = {"id": uuid4().hex, **payload.model_dump(), "delivery_id": delivery_id, "status": status}
    DELIVERIES.append(result)
    return result


@app.get("/deliveries")
def list_deliveries() -> list[dict]:
    return DELIVERIES
