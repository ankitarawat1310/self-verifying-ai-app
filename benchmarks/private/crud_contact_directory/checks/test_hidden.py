def _create(client, uid, **over):
    body = {"email": f"{uid('c')}@example.com", "display_name": "Ada Lovelace"}
    body.update(over)
    return client.post("/contacts", json=body)


def test_create_returns_201_with_id_and_fields(client, uid):
    """[functional] Creating a valid contact returns 201 with an id and the submitted fields."""
    email = f"{uid('ada')}@example.com"
    r = client.post("/contacts", json={"email": email, "display_name": "Ada"})
    assert r.status_code == 201
    body = r.json()
    assert body.get("id")
    assert body["email"].lower() == email.lower() and body["display_name"] == "Ada"


def test_created_contact_is_readable_and_listed(client, uid):
    """[functional] A created contact can be read by its returned id and appears in the list."""
    created = _create(client, uid).json()
    read = client.get(f"/contacts/{created['id']}")
    assert read.status_code == 200 and read.json()["id"] == created["id"]
    assert created["id"] in [c["id"] for c in client.get("/contacts").json()]


def test_update_changes_name_and_keeps_id(client, uid):
    """[functional] PATCH changes the display name and the stored record keeps the same id."""
    created = _create(client, uid).json()
    r = client.patch(f"/contacts/{created['id']}", json={"display_name": "Countess Ada"})
    assert r.status_code == 200 and r.json()["id"] == created["id"]
    assert client.get(f"/contacts/{created['id']}").json()["display_name"] == "Countess Ada"


def test_delete_then_read_is_404(client, uid):
    """[functional] DELETE returns 204 and the contact is gone afterwards."""
    created = _create(client, uid).json()
    assert client.delete(f"/contacts/{created['id']}").status_code == 204
    assert client.get(f"/contacts/{created['id']}").status_code == 404
    assert created["id"] not in [c["id"] for c in client.get("/contacts").json()]


def test_unknown_id_is_404(client, uid):
    """[functional] Reading, updating or deleting an unknown id returns 404 (while the routes do exist)."""
    assert _create(client, uid).status_code == 201
    assert client.get("/contacts/does-not-exist").status_code == 404
    assert client.patch("/contacts/does-not-exist", json={"display_name": "X"}).status_code == 404
    assert client.delete("/contacts/does-not-exist").status_code == 404


def test_duplicate_email_ignoring_case_is_409(client, uid):
    """[safety] A second contact whose email differs only in letter case is rejected with 409."""
    email = f"{uid('dup')}@example.com"
    assert _create(client, uid, email=email).status_code == 201
    assert _create(client, uid, email=email.upper()).status_code == 409


def test_update_cannot_take_another_contacts_email(client, uid):
    """[safety] Changing a contact's email to one already used (any case) is 409 and changes nothing."""
    first = _create(client, uid).json()
    second = _create(client, uid).json()
    r = client.patch(f"/contacts/{second['id']}", json={"email": first["email"].upper()})
    assert r.status_code == 409
    assert client.get(f"/contacts/{second['id']}").json()["email"].lower() == second["email"].lower()


def test_invalid_email_is_422(client, uid):
    """[safety] A malformed email address is rejected with 422."""
    assert _create(client, uid, email="not-an-email").status_code == 422


def test_update_with_invalid_email_is_422(client, uid):
    """[safety] PATCH with a malformed email is rejected with 422 and the stored email is unchanged."""
    created = _create(client, uid).json()
    assert client.patch(f"/contacts/{created['id']}", json={"email": "not-an-email"}).status_code == 422
    assert client.get(f"/contacts/{created['id']}").json()["email"].lower() == created["email"].lower()


def test_blank_display_name_is_422(client, uid):
    """[safety] An empty or whitespace-only display name is rejected with 422 on create and update."""
    assert _create(client, uid, display_name="").status_code == 422
    assert _create(client, uid, display_name="   ").status_code == 422
    created = _create(client, uid, display_name="Original Name").json()
    assert client.patch(f"/contacts/{created['id']}", json={"display_name": ""}).status_code == 422
    assert client.patch(f"/contacts/{created['id']}", json={"display_name": "   "}).status_code == 422
    assert client.get(f"/contacts/{created['id']}").json()["display_name"] == "Original Name"


def test_unknown_fields_are_rejected(client, uid):
    """[safety] Undeclared body fields (for example admin or id) are rejected with 422 on create and update."""
    assert _create(client, uid, admin=True).status_code == 422
    created = _create(client, uid).json()
    assert client.patch(f"/contacts/{created['id']}", json={"id": "hijack"}).status_code == 422
    assert client.get(f"/contacts/{created['id']}").status_code == 200


def test_missing_required_fields_is_422(client):
    """[safety] Creating a contact without email or display name is rejected with 422."""
    assert client.post("/contacts", json={"display_name": "No Email"}).status_code == 422
    assert client.post("/contacts", json={"email": "someone@example.com"}).status_code == 422
