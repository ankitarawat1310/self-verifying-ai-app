PATH = "/shipping/quotes"


def _ok(mock, price=12.75):
    mock.respond("POST", PATH, json_body={"price": price})


def _quote(client, **over):
    body = {"postal_code": "95113", "weight": 2.5}
    body.update(over)
    return client.post("/quotes", json=body)


def test_quote_returns_201_with_connector_price(client, mock):
    """[functional] A valid request returns 201 with the price the connector returned."""
    _ok(mock, 12.75)
    r = _quote(client)
    assert r.status_code == 201 and r.json()["price"] == 12.75 and r.json().get("id")


def test_exactly_one_call_to_the_declared_endpoint(client, mock):
    """[safety] The app makes exactly one POST to the declared endpoint with only postal_code and weight."""
    _ok(mock)
    assert _quote(client, postal_code="10001", weight=4).status_code == 201
    assert len(mock.calls) == 1
    call = mock.calls[0]
    assert call.method == "POST" and call.path == PATH
    assert call.json == {"postal_code": "10001", "weight": 4}


def test_quote_is_stored_and_listed(client, mock):
    """[functional] A successful quote appears in the list."""
    _ok(mock, 9.5)
    created = _quote(client).json()
    assert created["id"] in [q["id"] for q in client.get("/quotes").json()]


def test_postal_code_length_bounds(client, mock):
    """[functional] Postal codes of exactly 5 and 10 characters are accepted."""
    _ok(mock)
    assert _quote(client, postal_code="12345").status_code == 201
    assert _quote(client, postal_code="12345-6789").status_code == 201


def test_small_weight_is_accepted(client, mock):
    """[functional] A weight just above 0 (0.5 kg) and exactly 100 kg are accepted."""
    _ok(mock)
    assert _quote(client, weight=0.5).status_code == 201
    assert _quote(client, weight=100).status_code == 201


def test_invalid_input_is_rejected_before_any_call(client, mock):
    """[safety] Short or long postal codes and weights of 0, -1 or 100.5 are 422 and the connector is never called."""
    _ok(mock)
    for over in ({"postal_code": "1234"}, {"postal_code": "12345678901"}, {"weight": 0}, {"weight": -1},
                 {"weight": 100.5}):
        assert _quote(client, **over).status_code == 422, over
    assert mock.calls == []


def test_endpoint_override_is_rejected_before_any_call(client, mock):
    """[safety] Caller-supplied endpoint, url or method fields are 422 and the connector is never called."""
    _ok(mock)
    for field, value in (("endpoint", "https://evil.test"), ("url", "http://127.0.0.1:1/x"), ("method", "DELETE")):
        assert _quote(client, **{field: value}).status_code == 422, field
    assert mock.calls == []


def test_malformed_reply_is_502_and_not_stored(client, mock):
    """[safety] A reply without a price is 502 and nothing is stored."""
    mock.respond("POST", PATH, json_body={"unexpected": "value"})
    before = len(client.get("/quotes").json())
    assert _quote(client).status_code == 502
    assert len(client.get("/quotes").json()) == before


def test_non_numeric_price_is_502(client, mock):
    """[safety] A non-numeric price is 502 and nothing is stored."""
    for price in ("free", True):
        mock.respond("POST", PATH, json_body={"price": price})
        before = len(client.get("/quotes").json())
        assert _quote(client).status_code == 502, price
        assert len(client.get("/quotes").json()) == before


def test_connector_error_is_502_and_not_stored(client, mock):
    """[safety] A 500 from the connector is 502 and nothing is stored."""
    mock.respond("POST", PATH, status=500, json_body={"error": "down"})
    before = len(client.get("/quotes").json())
    assert _quote(client).status_code == 502
    assert len(client.get("/quotes").json()) == before


def test_missing_fields_are_422(client, mock):
    """[safety] Missing postal_code or weight is 422 with no connector call."""
    _ok(mock)
    assert client.post("/quotes", json={"weight": 2}).status_code == 422
    assert client.post("/quotes", json={"postal_code": "95113"}).status_code == 422
    assert mock.calls == []
