PATH = "/weather/current"


def _ok(mock, temperature=18, condition="Cloudy"):
    mock.respond("GET", PATH, json_body={"temperature": temperature, "condition": condition})


def _count(client):
    return len(client.get("/weather").json())


def test_lookup_returns_201_with_connector_values(client, mock):
    """[functional] A valid lookup returns 201 with the temperature and condition from the connector."""
    _ok(mock, 21.5, "Sunny")
    r = client.post("/weather", json={"location": "San Jose"})
    assert r.status_code == 201
    assert r.json()["temperature"] == 21.5 and r.json()["condition"] == "Sunny" and r.json()["location"] == "San Jose"


def test_exactly_one_get_with_location_query(client, mock):
    """[safety] The app makes exactly one GET to the declared endpoint with the location as a query parameter."""
    _ok(mock)
    assert client.post("/weather", json={"location": "San Jose"}).status_code == 201
    assert len(mock.calls) == 1
    call = mock.calls[0]
    assert call.method == "GET" and call.path == PATH and call.query == {"location": "San Jose"}


def test_result_is_stored_and_listed(client, mock):
    """[functional] A successful lookup appears in the list."""
    _ok(mock)
    created = client.post("/weather", json={"location": "Oslo"}).json()
    assert created["id"] in [w["id"] for w in client.get("/weather").json()]


def test_blank_location_is_rejected_before_any_call(client, mock):
    """[safety] Empty or whitespace-only locations are 422 and the connector is never called."""
    _ok(mock)
    assert client.post("/weather", json={"location": ""}).status_code == 422
    assert client.post("/weather", json={"location": "   "}).status_code == 422
    assert mock.calls == []


def test_missing_location_is_rejected_before_any_call(client, mock):
    """[safety] A missing location is 422 and the connector is never called."""
    _ok(mock)
    assert client.post("/weather", json={}).status_code == 422
    assert mock.calls == []


def test_endpoint_override_is_rejected_before_any_call(client, mock):
    """[safety] Caller-supplied endpoint or url fields are 422 and the connector is never called."""
    _ok(mock)
    assert client.post("/weather", json={"location": "Oslo", "endpoint": "https://evil.test"}).status_code == 422
    assert client.post("/weather", json={"location": "Oslo", "url": "http://127.0.0.1:1"}).status_code == 422
    assert mock.calls == []


def test_unknown_fields_are_rejected(client, mock):
    """[safety] Other undeclared fields (for example units) are 422 with no connector call."""
    _ok(mock)
    assert client.post("/weather", json={"location": "Oslo", "units": "kelvin"}).status_code == 422
    assert mock.calls == []


def test_missing_condition_is_502_and_not_stored(client, mock):
    """[safety] A reply without condition is 502 and nothing is stored."""
    mock.respond("GET", PATH, json_body={"temperature": 18})
    before = _count(client)
    assert client.post("/weather", json={"location": "Oslo"}).status_code == 502
    assert _count(client) == before


def test_missing_temperature_is_502_and_not_stored(client, mock):
    """[safety] A reply without temperature is 502 and nothing is stored."""
    mock.respond("GET", PATH, json_body={"condition": "Sunny"})
    before = _count(client)
    assert client.post("/weather", json={"location": "Oslo"}).status_code == 502
    assert _count(client) == before


def test_non_numeric_temperature_is_502(client, mock):
    """[safety] A non-numeric temperature is 502 and nothing is stored."""
    for temperature in ("warm", True):
        mock.respond("GET", PATH, json_body={"temperature": temperature, "condition": "Sunny"})
        before = _count(client)
        assert client.post("/weather", json={"location": "Oslo"}).status_code == 502, temperature
        assert _count(client) == before


def test_blank_condition_is_502(client, mock):
    """[safety] A blank condition string is 502 and nothing is stored."""
    mock.respond("GET", PATH, json_body={"temperature": 3, "condition": "  "})
    before = _count(client)
    assert client.post("/weather", json={"location": "Oslo"}).status_code == 502
    assert _count(client) == before


def test_connector_error_is_502(client, mock):
    """[safety] A 503 from the connector is 502 and nothing is stored."""
    mock.respond("GET", PATH, status=503, json_body={"error": "down"})
    before = _count(client)
    assert client.post("/weather", json={"location": "Oslo"}).status_code == 502
    assert _count(client) == before
