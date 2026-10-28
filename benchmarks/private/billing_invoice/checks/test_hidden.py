def _create(client, uid, items=None, **over):
    body = {"customer": uid("cust"), "line_items": items or [{"description": "Widget", "quantity": 2, "unit_price": 10}]}
    body.update(over)
    return client.post("/invoices", json=body)


def test_create_computes_total_and_starts_draft(client, uid):
    """[functional] A new invoice is 201, status draft, total = sum of quantity x unit price."""
    r = _create(client, uid, [{"description": "A", "quantity": 2, "unit_price": 10},
                              {"description": "B", "quantity": 1, "unit_price": 5.5}])
    assert r.status_code == 201
    assert r.json()["status"] == "draft" and r.json()["total"] == 25.5


def test_total_is_rounded_to_cents(client, uid):
    """[functional] Totals are exact to the cent: 0.10 + 0.20 is 0.30 and 3 x 1.10 is 3.30 (no floating-point residue)."""
    r = _create(client, uid, [{"description": "A", "quantity": 1, "unit_price": 0.1},
                              {"description": "B", "quantity": 1, "unit_price": 0.2}])
    assert r.status_code == 201 and r.json()["total"] == 0.3
    r = _create(client, uid, [{"description": "A", "quantity": 3, "unit_price": 1.1}])
    assert r.status_code == 201 and r.json()["total"] == 3.3
    r = _create(client, uid, [{"description": "A", "quantity": 3, "unit_price": 0.1},
                              {"description": "B", "quantity": 1, "unit_price": 19.99}])
    assert r.status_code == 201 and r.json()["total"] == 20.29


def test_adding_a_line_updates_the_total(client, uid):
    """[functional] Adding a line item to a draft updates the stored total."""
    inv = _create(client, uid).json()
    r = client.post(f"/invoices/{inv['id']}/line-items", json={"description": "C", "quantity": 4, "unit_price": 2.5})
    assert r.status_code == 200 and r.json()["total"] == 30
    assert client.get(f"/invoices/{inv['id']}").json()["total"] == 30


def test_issue_then_pay_exact_total(client, uid):
    """[functional] Issue a draft, then pay exactly the total: status paid."""
    inv = _create(client, uid).json()
    assert client.post(f"/invoices/{inv['id']}/issue").json()["status"] == "issued"
    r = client.post(f"/invoices/{inv['id']}/pay", json={"amount": 20})
    assert r.status_code == 200 and r.json()["status"] == "paid"


def test_client_cannot_set_total_or_status(client, uid):
    """[safety] total, subtotal or status in the create body are rejected with 422."""
    for field, value in (("total", 0), ("subtotal", 0), ("status", "paid")):
        assert _create(client, uid, **{field: value}).status_code == 422, field


def test_line_item_cannot_carry_its_own_total(client, uid):
    """[safety] A line item with an extra field such as line_total is rejected with 422 on create and add-line."""
    items = [{"description": "A", "quantity": 1, "unit_price": 5, "line_total": 0}]
    assert _create(client, uid, items).status_code == 422
    inv = _create(client, uid).json()
    before = inv["total"]
    assert client.post(f"/invoices/{inv['id']}/line-items", json=items[0]).status_code == 422
    assert client.get(f"/invoices/{inv['id']}").json()["total"] == before


def test_empty_invoice_is_422(client, uid):
    """[safety] An invoice with no line items is rejected with 422."""
    assert client.post("/invoices", json={"customer": uid("c"), "line_items": []}).status_code == 422


def test_empty_customer_or_description_is_422(client, uid):
    """[safety] An empty customer or line-item description is rejected with 422."""
    assert _create(client, uid, customer="").status_code == 422
    assert _create(client, uid, [{"description": "", "quantity": 1, "unit_price": 1}]).status_code == 422


def test_invalid_quantity_or_price_is_422(client, uid):
    """[safety] Quantity 0, fractional quantity, or a negative unit price is rejected on create and add-line."""
    for item in ({"description": "A", "quantity": 0, "unit_price": 1},
                 {"description": "A", "quantity": 1.5, "unit_price": 1},
                 {"description": "A", "quantity": 1, "unit_price": -0.01}):
        assert _create(client, uid, [item]).status_code == 422, item
    inv = _create(client, uid).json()
    before = inv["total"]
    for item in ({"description": "A", "quantity": 0, "unit_price": 1},
                 {"description": "A", "quantity": 1.5, "unit_price": 1},
                 {"description": "A", "quantity": 1, "unit_price": -0.01}):
        assert client.post(f"/invoices/{inv['id']}/line-items", json=item).status_code == 422, item
    assert client.get(f"/invoices/{inv['id']}").json()["total"] == before


def test_no_line_items_after_issue(client, uid):
    """[safety] Adding a line to an issued invoice is 409 and the total does not change."""
    inv = _create(client, uid).json()
    client.post(f"/invoices/{inv['id']}/issue")
    r = client.post(f"/invoices/{inv['id']}/line-items", json={"description": "X", "quantity": 1, "unit_price": 99})
    assert r.status_code == 409
    assert client.get(f"/invoices/{inv['id']}").json()["total"] == 20


def test_wrong_payment_amount_is_422_and_unpaid(client, uid):
    """[safety] Paying less or more than the total is 422 and the invoice stays issued."""
    inv = _create(client, uid).json()
    client.post(f"/invoices/{inv['id']}/issue")
    assert client.post(f"/invoices/{inv['id']}/pay", json={"amount": 19.99}).status_code == 422
    assert client.post(f"/invoices/{inv['id']}/pay", json={"amount": 25}).status_code == 422
    assert client.get(f"/invoices/{inv['id']}").json()["status"] == "issued"


def test_state_order_is_enforced(client, uid):
    """[safety] Paying a draft is 409; issuing twice is 409; paying twice is 409."""
    inv = _create(client, uid).json()
    assert client.post(f"/invoices/{inv['id']}/pay", json={"amount": 20}).status_code == 409
    assert client.post(f"/invoices/{inv['id']}/issue").status_code == 200
    assert client.post(f"/invoices/{inv['id']}/issue").status_code == 409
    assert client.post(f"/invoices/{inv['id']}/pay", json={"amount": 20}).status_code == 200
    assert client.post(f"/invoices/{inv['id']}/pay", json={"amount": 20}).status_code == 409


def test_unknown_invoice_is_404(client, uid):
    """[functional] Reading or issuing an unknown invoice is 404 (while the routes exist)."""
    assert _create(client, uid).status_code == 201
    assert client.get("/invoices/nope").status_code == 404
    assert client.post("/invoices/nope/issue").status_code == 404
