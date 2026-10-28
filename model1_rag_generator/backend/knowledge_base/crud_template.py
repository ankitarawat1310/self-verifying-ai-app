"""CRUD API Template using FastAPI and Pydantic v2."""

from typing import List, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field


class ItemSchema(BaseModel):
    id: Optional[int] = Field(default=None)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    price: float = Field(..., gt=0)


class ItemStore:
    def __init__(self):
        self._db: dict[int, dict] = {}
        self._counter: int = 1

    def create(self, data: ItemSchema) -> dict:
        item_id = self._counter
        item_data = data.model_dump()
        item_data["id"] = item_id
        self._db[item_id] = item_data
        self._counter += 1
        return item_data

    def get_by_id(self, item_id: int) -> Optional[dict]:
        return self._db.get(item_id)

    def list_all(self) -> List[dict]:
        return list(self._db.values())


app = FastAPI(title="CRUD Service Template")
db = ItemStore()


@app.post("/items", response_model=ItemSchema, status_code=status.HTTP_201_CREATED)
async def create_item_endpoint(item: ItemSchema):
    return db.create(item)


@app.get("/items/{item_id}", response_model=ItemSchema)
async def read_item_endpoint(item_id: int):
    found = db.get_by_id(item_id)
    if not found:
        raise HTTPException(status_code=404, detail="Not found")
    return found
