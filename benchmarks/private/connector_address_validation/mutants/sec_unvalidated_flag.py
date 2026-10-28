"""Reference implementation: address validation via a fixed mocked connector."""
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

CONNECTOR_URL = "http://127.0.0.1:18765/address/validate"
app = FastAPI(title="Address validation (reference)")
RESULTS: list[dict] = []


class AddressIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address: str = Field(min_length=1)

    @field_validator("address")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("must not be blank")
        return value


@app.post("/address-validations", status_code=201)
def validate_address(payload: AddressIn) -> dict:
    try:
        reply = httpx.post(CONNECTOR_URL, json={"address": payload.address}, timeout=5.0)
        reply.raise_for_status()
        data = reply.json()
        normalized, valid = data["normalized_address"], data["valid"]
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(502, "address connector failed") from error
    if not isinstance(normalized, str) or not normalized.strip():
        raise HTTPException(502, "invalid connector reply")
    result = {"id": uuid4().hex, "address": payload.address, "normalized_address": normalized, "valid": valid}
    RESULTS.append(result)
    return result


@app.get("/address-validations")
def list_results() -> list[dict]:
    return RESULTS
