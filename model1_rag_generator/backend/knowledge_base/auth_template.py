"""Authentication patterns for small FastAPI services."""

from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.security import APIKeyHeader

API_KEY_NAME = "X-API-Key"
VALID_API_KEYS = {"secret-key-123", "admin-token-456"}

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    if not api_key or api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return api_key


app = FastAPI(title="Auth Template")


@app.get("/protected-resource")
async def protected_endpoint(api_key: str = Depends(verify_api_key)):
    return {"status": "authenticated"}
