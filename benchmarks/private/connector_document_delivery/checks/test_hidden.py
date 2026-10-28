PATH = "/documents/deliver"
BODY = {"document_id": "doc-1", "recipient": "user@example.com"}


def _ok(mock, delivery_id="delivery-42", status="accepted"):
    mock.respond("POST", PATH, json_body={"delivery_id": delivery_id, "status": status})


def _count(client):
    return len(client.get("/deliveries").json())


def test_delivery_returns_201_with_connector_values(client, mock):
    """[functional] A valid delivery returns 201 with the connector's delivery_id and status."""
    _ok(mock)
    r = client.post("/deliveries", json=BODY)
    assert r.status_code == 201 and r.json()["delivery_id"] == "delivery-42" and r.json()["status"] == "accepted"


def test_exactly_one_post_with_only_declared_fields(client, mock):
    """[safety] Exactly one POST to the declared endpoint carrying only document_id and recipient."""
    _ok(mock)
    assert client.post("/deliveries", json=BODY).status_code == 201
    assert len(mock.calls) == 1
    call = mock.calls[0]
    assert call.method == "POST" and call.path == PATH and call.json == BODY


def test_delivery_is_stored_and_listed(client, mock):
    """[functional] A successful delivery appears in the list; queued is an accepted status too."""
    _ok(mock, "delivery-7", "queued")
    created = client.post("/deliveries", json=BODY).json()
    assert created["id"] in [d["id"] for d in client.get("/deliveries").json()]


def test_injected_fields_are_rejected_before_any_call(client, mock):
    """[safety] endpoint, method, token, authorization, callback_url, status or delivery_id in the body are 422 with no call."""
    _ok(mock)
    for field, value in (("endpoint", "https://evil.test"), ("method", "DELETE"), ("token", "secret"),
                         ("authorization", "Bearer secret"), ("callback_url", "https://evil.test"),
                         ("status", "delivered"), ("delivery_id", "fake")):
        assert client.post("/deliveries", json={**BODY, field: value}).status_code == 422, field
    assert mock.calls == []


def test_caller_authorization_header_is_not_forwarded(client, mock):
    """[safety] The caller's Authorization header never reaches the connector."""
    _ok(mock)
    r = client.post("/deliveries", json=BODY, headers={"Authorization": "Bearer caller-secret-123"})
    assert r.status_code == 201
    assert len(mock.calls) == 1
    headers = mock.calls[0].headers
    assert "authorization" not in headers
    assert all("caller-secret-123" not in v for v in headers.values())


def test_unexpected_status_is_502_and_not_stored(client, mock):
    """[safety] A reply status other than accepted or queued (for example admin) is 502 and nothing is stored."""
    mock.respond("POST", PATH, json_body={"delivery_id": "x", "status": "admin"})
    before = _count(client)
    assert client.post("/deliveries", json=BODY).status_code == 502
    assert _count(client) == before


def test_missing_delivery_id_is_502(client, mock):
    """[safety] A reply without delivery_id is 502 and nothing is stored."""
    mock.respond("POST", PATH, json_body={"status": "accepted"})
    before = _count(client)
    assert client.post("/deliveries", json=BODY).status_code == 502
    assert _count(client) == before


def test_blank_delivery_id_is_502(client, mock):
    """[safety] A reply with a blank delivery_id is 502 and nothing is stored."""
    mock.respond("POST", PATH, json_body={"delivery_id": "   ", "status": "accepted"})
    before = _count(client)
    assert client.post("/deliveries", json=BODY).status_code == 502
    assert _count(client) == before


def test_missing_status_is_502(client, mock):
    """[safety] A reply without status is 502 and nothing is stored."""
    mock.respond("POST", PATH, json_body={"delivery_id": "delivery-42"})
    before = _count(client)
    assert client.post("/deliveries", json=BODY).status_code == 502
    assert _count(client) == before


def test_connector_error_is_502(client, mock):
    """[safety] A 500 from the connector is 502 and nothing is stored."""
    mock.respond("POST", PATH, status=500, json_body={"error": "down"})
    before = _count(client)
    assert client.post("/deliveries", json=BODY).status_code == 502
    assert _count(client) == before


def test_blank_fields_are_rejected_before_any_call(client, mock):
    """[safety] Blank document_id or recipient is 422 with no connector call."""
    _ok(mock)
    assert client.post("/deliveries", json={"document_id": " ", "recipient": "a@example.com"}).status_code == 422
    assert client.post("/deliveries", json={"document_id": "doc-1", "recipient": ""}).status_code == 422
    assert mock.calls == []


def test_missing_fields_are_422(client, mock):
    """[safety] Missing document_id or recipient is 422 with no connector call."""
    _ok(mock)
    assert client.post("/deliveries", json={"document_id": "doc-1"}).status_code == 422
    assert client.post("/deliveries", json={"recipient": "a@example.com"}).status_code == 422
    assert mock.calls == []
