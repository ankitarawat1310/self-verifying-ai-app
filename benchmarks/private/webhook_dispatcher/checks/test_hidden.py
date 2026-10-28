PATH = "/hooks/receive"


def _send(client, type_="order.created", payload=None, **over):
    body = {"type": type_, "payload": payload if payload is not None else {"order_id": "o-1", "total": 42}}
    body.update(over)
    return client.post("/events", json=body)


def test_delivered_on_first_attempt(client, mock):
    """[functional] With a healthy receiver, the event is 201, delivered, 1 attempt, 1 call."""
    mock.respond("POST", PATH, json_body={"ok": True})
    r = _send(client)
    assert r.status_code == 201 and r.json()["status"] == "delivered" and r.json()["attempts"] == 1
    assert len(mock.calls) == 1


def test_delivery_carries_id_type_and_payload(client, mock):
    """[safety] The receiver gets exactly {event_id, type, payload}, and event_id matches the stored event."""
    mock.respond("POST", PATH, json_body={})
    r = _send(client, "order.cancelled", {"order_id": "o-9"})
    call = mock.calls[0]
    assert call.method == "POST" and call.path == PATH
    assert call.json == {"event_id": r.json()["id"], "type": "order.cancelled", "payload": {"order_id": "o-9"}}


def test_retries_until_success(client, mock):
    """[functional] Receiver fails twice then succeeds: delivered after exactly 3 attempts."""
    mock.respond_sequence("POST", PATH, [(500, {}), (503, {}), (200, {})])
    r = _send(client)
    assert r.json()["status"] == "delivered" and r.json()["attempts"] == 3
    assert len(mock.calls) == 3


def test_gives_up_after_three_attempts(client, mock):
    """[safety] A receiver that always fails gets exactly 3 attempts, then the event is dead_lettered."""
    mock.respond("POST", PATH, status=500, json_body={})
    r = _send(client)
    assert r.status_code == 201 and r.json()["status"] == "dead_lettered" and r.json()["attempts"] == 3
    assert len(mock.calls) == 3


def test_client_error_status_also_counts_as_failure(client, mock):
    """[safety] A 4xx answer is not success: retried, and after 3 attempts dead_lettered."""
    mock.respond("POST", PATH, status=410, json_body={})
    r = _send(client)
    assert r.json()["status"] == "dead_lettered" and len(mock.calls) == 3


def test_dead_letters_list_only_failed_events(client, mock):
    """[functional] A dead-lettered event appears under /dead-letters; a delivered one does not."""
    mock.respond("POST", PATH, status=500, json_body={})
    failed = _send(client).json()
    mock.respond("POST", PATH, status=200, json_body={})
    delivered = _send(client).json()
    ids = [e["id"] for e in client.get("/dead-letters").json()]
    assert failed["id"] in ids and delivered["id"] not in ids


def test_event_can_be_read(client, mock):
    """[functional] A stored event can be read by id; unknown ids are 404."""
    mock.respond("POST", PATH, json_body={})
    ev = _send(client).json()
    assert client.get(f"/events/{ev['id']}").json()["status"] == "delivered"
    assert client.get("/events/nope").status_code == 404


def test_unknown_event_type_is_rejected_before_any_call(client, mock):
    """[safety] An event type other than order.created or order.cancelled is 422 with no delivery."""
    mock.respond("POST", PATH, json_body={})
    assert _send(client, "user.deleted").status_code == 422
    assert mock.calls == []


def test_payload_must_be_an_object(client, mock):
    """[safety] A payload that is a string or a list is 422 with no delivery."""
    mock.respond("POST", PATH, json_body={})
    assert _send(client, payload="text").status_code == 422
    assert _send(client, payload=[1, 2]).status_code == 422
    assert mock.calls == []


def test_caller_cannot_choose_url_status_or_attempts(client, mock):
    """[safety] url, target, status or max_attempts in the body are 422 with no delivery."""
    mock.respond("POST", PATH, json_body={})
    for field, value in (("url", "https://evil.test"), ("target", "http://127.0.0.1:1"), ("status", "delivered"),
                         ("max_attempts", 100)):
        assert _send(client, **{field: value}).status_code == 422, field
    assert mock.calls == []


def test_recovers_on_the_second_attempt(client, mock):
    """[functional] Receiver fails once then succeeds: delivered after exactly 2 attempts and not dead-lettered."""
    mock.respond_sequence("POST", PATH, [(500, {}), (200, {})])
    r = _send(client)
    assert r.status_code == 201 and r.json()["status"] == "delivered" and r.json()["attempts"] == 2
    assert len(mock.calls) == 2
    assert r.json()["id"] not in [e["id"] for e in client.get("/dead-letters").json()]


def test_any_2xx_answer_counts_as_delivered(client, mock):
    """[functional] A 200, 201 or 202 answer from the receiver is success: delivered on the first attempt."""
    for status in (200, 201, 202):
        mock.reset()
        mock.respond("POST", PATH, status=status, json_body={"ok": True})
        r = _send(client)
        assert r.json()["status"] == "delivered" and r.json()["attempts"] == 1, status
        assert len(mock.calls) == 1, status


def test_every_attempt_resends_the_same_event(client, mock):
    """[safety] All three attempts carry the same event id, type and payload."""
    mock.respond_sequence("POST", PATH, [(500, {}), (500, {}), (200, {})])
    r = _send(client, "order.created", {"order_id": "o-77", "items": [1, 2]})
    expected = {"event_id": r.json()["id"], "type": "order.created", "payload": {"order_id": "o-77", "items": [1, 2]}}
    assert len(mock.calls) == 3 and all(call.json == expected for call in mock.calls)


def test_response_fields_match_the_interface(client, mock):
    """[functional] Event responses, stored events and dead letters carry id, type, payload, status and attempts; ids are unique."""
    fields = {"id", "type", "payload", "status", "attempts"}
    mock.respond("POST", PATH, status=500, json_body={})
    failed = _send(client, "order.cancelled", {"order_id": "o-5"})
    mock.respond("POST", PATH, status=200, json_body={})
    ok = _send(client)
    assert failed.status_code == ok.status_code == 201 and fields <= set(failed.json()) and fields <= set(ok.json())
    assert failed.json()["id"] != ok.json()["id"]
    assert failed.json()["type"] == "order.cancelled" and failed.json()["payload"] == {"order_id": "o-5"}
    stored = client.get(f"/events/{failed.json()['id']}").json()
    assert fields <= set(stored) and stored["status"] == "dead_lettered" and stored["attempts"] == 3
    dead = [e for e in client.get("/dead-letters").json() if e["id"] == failed.json()["id"]]
    assert len(dead) == 1 and fields <= set(dead[0])
    assert dead[0]["status"] == "dead_lettered" and dead[0]["attempts"] == 3


def test_missing_type_or_payload_is_422_before_any_call(client, mock):
    """[safety] A missing type, a missing payload, or a null or numeric payload is 422 with no delivery."""
    mock.respond("POST", PATH, json_body={})
    assert client.post("/events", json={"payload": {"a": 1}}).status_code == 422
    assert client.post("/events", json={"type": "order.created"}).status_code == 422
    assert client.post("/events", json={"type": "order.created", "payload": None}).status_code == 422
    assert client.post("/events", json={"type": "order.created", "payload": 7}).status_code == 422
    assert mock.calls == []


def test_empty_and_nested_payloads_are_delivered_unchanged(client, mock):
    """[functional] An empty object and a nested object are accepted and delivered exactly as given."""
    mock.respond("POST", PATH, json_body={})
    nested = {"order": {"id": "o-1", "lines": [{"sku": "a", "qty": 2}], "note": None, "paid": True}}
    for payload in ({}, nested):
        start = len(mock.calls)
        r = _send(client, payload=payload)
        assert r.status_code == 201 and r.json()["payload"] == payload and r.json()["status"] == "delivered"
        assert len(mock.calls) == start + 1 and mock.calls[-1].json["payload"] == payload


def test_a_3xx_answer_is_not_success(client, mock):
    """[safety] Only 2xx is success: a 300 answer is a failure, retried, and after 3 attempts the event is dead_lettered."""
    mock.respond("POST", PATH, status=300, json_body={})
    r = _send(client)
    assert r.json()["status"] == "dead_lettered" and r.json()["attempts"] == 3
    assert len(mock.calls) == 3
