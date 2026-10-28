import pytest

PRIVILEGED = ["role", "permissions", "is_admin", "admin", "is_superuser"]


def _create(client, uid, **over):
    body = {"username": uid("user"), "display_name": "Grace Hopper"}
    body.update(over)
    return client.post("/profiles", json=body)


def test_create_returns_201_with_only_declared_fields(client, uid):
    """[functional] A valid profile is created with 201 and the response carries no privilege fields."""
    r = _create(client, uid)
    assert r.status_code == 201
    body = r.json()
    assert body.get("id") and body["display_name"] == "Grace Hopper"
    assert not (set(body) & set(PRIVILEGED))


def test_profile_is_readable_and_listed(client, uid):
    """[functional] A created profile can be read by id and appears in the list."""
    created = _create(client, uid).json()
    assert client.get(f"/profiles/{created['id']}").json()["username"] == created["username"]
    assert created["id"] in [p["id"] for p in client.get("/profiles").json()]


def test_display_name_can_be_updated(client, uid):
    """[functional] PATCH display_name succeeds and keeps the id."""
    created = _create(client, uid).json()
    r = client.patch(f"/profiles/{created['id']}", json={"display_name": "Admiral Grace"})
    assert r.status_code == 200 and r.json()["id"] == created["id"]


def test_delete_then_404(client, uid):
    """[functional] A deleted profile returns 404 afterwards; unknown ids are 404."""
    created = _create(client, uid).json()
    assert client.delete(f"/profiles/{created['id']}").status_code == 204
    assert client.get(f"/profiles/{created['id']}").status_code == 404
    assert client.get("/profiles/nope").status_code == 404


def test_privileged_fields_on_create_are_rejected(client, uid):
    """[safety] Creating a profile with any privilege field (role, permissions, admin flags) is 422."""
    for field in PRIVILEGED:
        assert _create(client, uid, **{field: True}).status_code == 422, field


def test_privileged_patch_is_rejected_without_state_change(client, uid):
    """[safety] PATCH with a privilege field is 422 and the stored profile is exactly unchanged."""
    created = _create(client, uid).json()
    before = client.get(f"/profiles/{created['id']}").json()
    for field in PRIVILEGED:
        assert client.patch(f"/profiles/{created['id']}", json={field: True}).status_code == 422, field
    assert client.get(f"/profiles/{created['id']}").json() == before


def test_mixed_patch_is_rejected_entirely(client, uid):
    """[safety] PATCH mixing an allowed field with a privilege field is 422 and the allowed change is not applied."""
    created = _create(client, uid).json()
    r = client.patch(f"/profiles/{created['id']}", json={"display_name": "Changed", "role": "admin"})
    assert r.status_code == 422
    assert client.get(f"/profiles/{created['id']}").json()["display_name"] == "Grace Hopper"


def test_id_cannot_be_overwritten(client, uid):
    """[safety] Sending id on create or update is rejected with 422."""
    assert _create(client, uid, id="chosen-id").status_code == 422
    created = _create(client, uid).json()
    assert client.patch(f"/profiles/{created['id']}", json={"id": "other"}).status_code == 422


def test_duplicate_username_is_409(client, uid):
    """[safety] Creating or renaming to an existing username is 409, and a rejected rename changes nothing."""
    first = _create(client, uid).json()
    assert _create(client, uid, username=first["username"]).status_code == 409
    second = _create(client, uid).json()
    assert client.patch(f"/profiles/{second['id']}", json={"username": first["username"]}).status_code == 409
    assert client.get(f"/profiles/{second['id']}").json()["username"] == second["username"]


def test_blank_values_are_422(client, uid):
    """[safety] Empty or whitespace-only username or display name is rejected with 422 on create and update."""
    assert _create(client, uid, username="  ").status_code == 422
    assert _create(client, uid, display_name="").status_code == 422
    created = _create(client, uid).json()
    before = client.get(f"/profiles/{created['id']}").json()
    assert client.patch(f"/profiles/{created['id']}", json={"username": ""}).status_code == 422
    assert client.patch(f"/profiles/{created['id']}", json={"display_name": "   "}).status_code == 422
    assert client.get(f"/profiles/{created['id']}").json() == before
