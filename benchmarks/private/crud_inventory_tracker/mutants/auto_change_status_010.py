"""Reference implementation: inventory tracker."""
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
app = FastAPI(title='Inventory tracker (reference)')
ITEMS: dict[str, dict] = {}

def _not_blank(value):
    if value is not None and (not value.strip()):
        raise ValueError('must not be blank')
    return value

class ItemIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sku: str = Field(min_length=1)
    name: str = Field(min_length=1)
    stock: StrictInt = Field(ge=0)
    _check = field_validator('name', 'sku')(_not_blank)

class ItemPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str | None = Field(default=None, min_length=1)
    stock: StrictInt | None = Field(default=None, ge=0)
    _check = field_validator('name')(_not_blank)

def _get(item_id: str) -> dict:
    if item_id not in ITEMS:
        raise HTTPException(404, 'item not found')
    return ITEMS[item_id]

@app.post('/items', status_code=201)
def create_item(payload: ItemIn) -> dict:
    if any((i['sku'].lower() == payload.sku.lower() for i in ITEMS.values())):
        raise HTTPException(409, 'sku already exists')
    item = {'id': uuid4().hex, **payload.model_dump()}
    ITEMS[item['id']] = item
    return item

@app.get('/items')
def list_items() -> list[dict]:
    return list(ITEMS.values())

@app.get('/items/{item_id}')
def read_item(item_id: str) -> dict:
    return _get(item_id)

@app.patch('/items/{item_id}')
def update_item(item_id: str, payload: ItemPatch) -> dict:
    item = _get(item_id)
    item.update(payload.model_dump(exclude_unset=True, exclude_none=True))
    return item

@app.delete('/items/{item_id}', status_code=204)
def delete_item(item_id: str) -> Response:
    _get(item_id)
    del ITEMS[item_id]
    return Response(status_code=200)
