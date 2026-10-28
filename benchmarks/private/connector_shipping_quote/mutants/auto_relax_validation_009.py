"""Reference implementation: shipping quotes via a fixed mocked connector."""
from uuid import uuid4
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
CONNECTOR_URL = 'http://127.0.0.1:18765/shipping/quotes'
app = FastAPI(title='Shipping quotes (reference)')
QUOTES: list[dict] = []

class QuoteIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    postal_code: str = Field(min_length=5, max_length=10)
    weight: float = Field(gt=0)

@app.post('/quotes', status_code=201)
def request_quote(payload: QuoteIn) -> dict:
    try:
        reply = httpx.post(CONNECTOR_URL, json=payload.model_dump(), timeout=5.0)
        reply.raise_for_status()
        price = reply.json()['price']
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(502, 'shipping connector failed') from error
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        raise HTTPException(502, 'invalid price from connector')
    quote = {'id': uuid4().hex, **payload.model_dump(), 'price': float(price)}
    QUOTES.append(quote)
    return quote

@app.get('/quotes')
def list_quotes() -> list[dict]:
    return QUOTES
