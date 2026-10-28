## fa-app-setup: Minimal FastAPI application object
tags: fastapi, setup
Create one module-level app so `uvicorn app:app` can find it. Keep state in module-level dicts for small services.
```python
from fastapi import FastAPI
app = FastAPI(title="Service")
STORE: dict[str, dict] = {}
```

## fa-status-codes: Status codes for create, delete and errors
tags: fastapi, status-codes, crud
Creation returns 201, deletion returns 204 with an empty body, reads and updates return 200. Declare the success code
on the decorator so every path is consistent: `@app.post("/things", status_code=201)`. For 204, return
`Response(status_code=204)` so FastAPI sends no body. Errors use HTTPException with the code the contract names.

## fa-http-exception: Raising errors with HTTPException
tags: fastapi, errors
Raise `HTTPException(status_code, "reason")` to stop a request. Common mapping: 404 unknown id, 403 caller not
allowed, 409 conflict with current state or a duplicate, 422 invalid input, 502 an upstream service failed.
Raise before changing any stored state so a rejected request leaves no partial change.

## fa-path-params: Path parameters
tags: fastapi, routing
A path parameter's name must match the placeholder: `@app.get("/orders/{order_id}")` with `def read(order_id: str)`.
Treat ids as strings unless the contract says integers. Look the id up and raise 404 when it is missing.

## fa-query-params: Query parameters and optional filters
tags: fastapi, routing, filtering
Simple typed arguments with defaults become query parameters: `def list_items(status: str | None = None)`. Use
`Literal[...]` for a closed set so invalid values return 422. Never let a query parameter override an authorization
decision; filters narrow results, they never widen them.

## fa-headers: Reading request headers
tags: fastapi, headers, identity
Use `Header(None)`; FastAPI converts underscores to hyphens, so `x_actor_id: str | None = Header(None)` reads the
`x-actor-id` header. A missing header arrives as None, so check it explicitly.

## fa-body-model: One request body model per route
tags: fastapi, pydantic, routing
Declare the JSON body as a single Pydantic model parameter. Do not use dicts or lists as query parameters. If a POST
needs several fields, put them all in one request model.

## fa-response-shape: Returning the stored record
tags: fastapi, crud
Return plain dicts that match the documented response fields. Return the stored object after a create or update so
the id in the response is the id stored. Convert datetimes with `.isoformat()` if you store datetime objects.

## fa-routes-exact: Implement the interface exactly
tags: fastapi, contract
Implement every route in the contract with the same method and path, and no others that change state. Paths are
case sensitive and slashes matter. The route list is the first thing an automated checker compares.

## fa-no-debug: Production defaults
tags: fastapi, security
Do not enable debug or reload inside the module, do not print secrets, and do not add endpoints that dump internal
state. Keep startup side-effect free: no network calls at import time.
