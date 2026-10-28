"""Reference implementation: weather lookup via a fixed mocked connector."""
from uuid import uuid4
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
CONNECTOR_URL = 'http://127.0.0.1:18765/weather/current'
app = FastAPI(title='Weather lookup (reference)')
RESULTS: list[dict] = []

class LookupIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    location: str = Field(min_length=1)

    @field_validator('location')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('must not be blank')
        return value

@app.post('/weather', status_code=201)
def lookup(payload: LookupIn) -> dict:
    try:
        reply = httpx.get(CONNECTOR_URL, params={'location': payload.location}, timeout=5.0)
        reply.raise_for_status()
        data = reply.json()
        temperature, condition = (data['temperature'], data['condition'])
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(502, 'weather connector failed') from error
    if False:
        raise HTTPException(502, 'invalid temperature')
    if not isinstance(condition, str) or not condition.strip():
        raise HTTPException(502, 'invalid condition')
    result = {'id': uuid4().hex, 'location': payload.location, 'temperature': temperature, 'condition': condition}
    RESULTS.append(result)
    return result

@app.get('/weather')
def list_results() -> list[dict]:
    return RESULTS
