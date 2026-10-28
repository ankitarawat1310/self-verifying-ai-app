PATH = "/address/validate"


def _ok(mock, normalized="1 MAIN ST", valid=True):
    mock.respond("POST", PATH, json_body={"normalized_address": normalized, "valid": valid})


def _count(client):
    return len(client.get("/address-validations").json())


def test_validation_returns_201_with_connector_values(client, mock):
    """[functional] A valid request returns 201 with the normalized address and flag from the connector."""
    _ok(mock)
    r = client.post("/address-validations", json={"address": "1 Main St"})
    assert r.status_code == 201
    assert r.json()["normalized_address"] == "1 MAIN ST" and r.json()["valid"] is True


def test_exactly_one_post_with_only_the_address(client, mock):
    """[safety] Exactly one POST to the declared endpoint carrying only the address."""
    _ok(mock)
    assert client.post("/address-validations", json={"address": "1 Main St"}).status_code == 201
    assert len(mock.calls) == 1
    call = mock.calls[0]
    assert call.method == "POST" and call.path == PATH and call.json == {"address": "1 Main St"}


def test_result_is_stored_and_listed(client, mock):
    """[functional] A successful validation appears in the list."""
    _ok(mock)
    created = client.post("/address-validations", json={"address": "2 Elm Rd"}).json()
    assert created["id"] in [a["id"] for a in client.get("/address-validations").json()]


def test_invalid_address_result_is_still_stored(client, mock):
    """[functional] When the service says valid=false, the result is stored with valid false."""
    _ok(mock, "UNKNOWN", False)
    r = client.post("/address-validations", json={"address": "nowhere"})
    assert r.status_code == 201 and r.json()["valid"] is False


def test_blank_address_is_rejected_before_any_call(client, mock):
    """[safety] Empty or whitespace-only addresses are 422 with no connector call."""
    _ok(mock)
    assert client.post("/address-validations", json={"address": " "}).status_code == 422
    assert mock.calls == []


def test_endpoint_or_method_override_is_rejected(client, mock):
    """[safety] Caller-supplied endpoint or method fields are 422 with no connector call."""
    _ok(mock)
    for field, value in (("endpoint", "https://evil.test"), ("method", "DELETE")):
        assert client.post("/address-validations", json={"address": "1 Main St", field: value}).status_code == 422
    assert mock.calls == []


def test_missing_reply_field_is_502(client, mock):
    """[safety] A reply without valid is 502 and nothing is stored."""
    mock.respond("POST", PATH, json_body={"normalized_address": "1 MAIN ST"})
    before = _count(client)
    assert client.post("/address-validations", json={"address": "1 Main St"}).status_code == 502
    assert _count(client) == before


def test_missing_normalized_address_is_502(client, mock):
    """[safety] A reply without normalized_address is 502 and nothing is stored."""
    mock.respond("POST", PATH, json_body={"valid": True})
    before = _count(client)
    assert client.post("/address-validations", json={"address": "1 Main St"}).status_code == 502
    assert _count(client) == before


def test_non_boolean_valid_flag_is_502(client, mock):
    """[safety] A valid flag that is not a boolean (for example "yes") is 502 and nothing is stored."""
    mock.respond("POST", PATH, json_body={"normalized_address": "1 MAIN ST", "valid": "yes"})
    before = _count(client)
    assert client.post("/address-validations", json={"address": "1 Main St"}).status_code == 502
    assert _count(client) == before


def test_blank_normalized_address_is_502(client, mock):
    """[safety] A blank normalized_address is 502 and nothing is stored."""
    mock.respond("POST", PATH, json_body={"normalized_address": "", "valid": True})
    before = _count(client)
    assert client.post("/address-validations", json={"address": "1 Main St"}).status_code == 502
    assert _count(client) == before


def test_connector_error_is_502(client, mock):
    """[safety] A 500 from the connector is 502 and nothing is stored."""
    mock.respond("POST", PATH, status=500, json_body={})
    before = _count(client)
    assert client.post("/address-validations", json={"address": "1 Main St"}).status_code == 502
    assert _count(client) == before
