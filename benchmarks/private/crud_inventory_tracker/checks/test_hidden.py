def _create(client, uid, **over):
    body = {"sku": uid("SKU-"), "name": "Mouse", "stock": 3}
    body.update(over)
    return client.post("/items", json=body)


def test_create_returns_201_with_fields(client, uid):
    """[functional] A valid item is created with 201 and echoes sku, name and stock."""
    sku = uid("SKU-")
    r = client.post("/items", json={"sku": sku, "name": "Keyboard", "stock": 0})
    assert r.status_code == 201
    body = r.json()
    assert body.get("id") and body["sku"] == sku and body["name"] == "Keyboard" and body["stock"] == 0


def test_item_is_readable_and_listed(client, uid):
    """[functional] A created item can be read by id and appears in the list."""
    created = _create(client, uid).json()
    assert client.get(f"/items/{created['id']}").json()["sku"] == created["sku"]
    assert created["id"] in [i["id"] for i in client.get("/items").json()]


def test_patch_updates_stock(client, uid):
    """[functional] PATCH can set stock to a new nonnegative integer."""
    created = _create(client, uid).json()
    r = client.patch(f"/items/{created['id']}", json={"stock": 42})
    assert r.status_code == 200
    assert client.get(f"/items/{created['id']}").json()["stock"] == 42


def test_delete_then_404(client, uid):
    """[functional] A deleted item returns 404 afterwards; unknown ids are 404."""
    created = _create(client, uid).json()
    assert client.delete(f"/items/{created['id']}").status_code == 204
    assert client.get(f"/items/{created['id']}").status_code == 404
    assert client.patch("/items/nope", json={"stock": 1}).status_code == 404


def test_negative_stock_is_422(client, uid):
    """[safety] Negative stock is rejected with 422 on create."""
    assert _create(client, uid, stock=-1).status_code == 422


def test_fractional_stock_is_422(client, uid):
    """[safety] Non-integer stock is rejected on create and update, with stored stock unchanged."""
    assert _create(client, uid, stock=1.5).status_code == 422
    created = _create(client, uid, stock=5).json()
    assert client.patch(f"/items/{created['id']}", json={"stock": 1.5}).status_code == 422
    assert client.get(f"/items/{created['id']}").json()["stock"] == 5


def test_blank_name_is_422(client, uid):
    """[safety] Empty or whitespace-only names are rejected on create and update, with stored name unchanged."""
    assert _create(client, uid, name="").status_code == 422
    assert _create(client, uid, name="   ").status_code == 422
    created = _create(client, uid, name="Mouse").json()
    assert client.patch(f"/items/{created['id']}", json={"name": ""}).status_code == 422
    assert client.patch(f"/items/{created['id']}", json={"name": "   "}).status_code == 422
    assert client.get(f"/items/{created['id']}").json()["name"] == "Mouse"


def test_duplicate_sku_ignoring_case_is_409(client, uid):
    """[safety] A SKU that differs only in letter case from an existing one is rejected with 409."""
    sku = uid("sku-")
    assert _create(client, uid, sku=sku).status_code == 201
    assert _create(client, uid, sku=sku.upper()).status_code == 409


def test_patch_to_negative_stock_is_rejected_and_unchanged(client, uid):
    """[safety] PATCH with negative stock is 422 and the stored stock stays the same."""
    created = _create(client, uid, stock=5).json()
    assert client.patch(f"/items/{created['id']}", json={"stock": -3}).status_code == 422
    assert client.get(f"/items/{created['id']}").json()["stock"] == 5


def test_sku_cannot_be_changed(client, uid):
    """[safety] Sending sku in PATCH is rejected with 422 and the SKU is unchanged."""
    created = _create(client, uid).json()
    assert client.patch(f"/items/{created['id']}", json={"sku": uid("NEW-")}).status_code == 422
    assert client.get(f"/items/{created['id']}").json()["sku"] == created["sku"]


def test_unknown_fields_are_rejected(client, uid):
    """[safety] Undeclared fields on create and update are rejected with 422."""
    assert _create(client, uid, price=9.99).status_code == 422
    created = _create(client, uid).json()
    assert client.patch(f"/items/{created['id']}", json={"price": 9.99}).status_code == 422
