def _create(client, actor, who, role="user", **over):
    body = {"title": "Notes", "body": "secret plans"}
    body.update(over)
    return client.post("/documents", json=body, headers=actor(who, role))


def test_create_sets_owner_from_header(client, actor, uid):
    """[functional] A created document is 201 and owned by the caller."""
    who = uid("u")
    r = _create(client, actor, who)
    assert r.status_code == 201 and r.json()["owner_id"] == who


def test_owner_can_read_update_and_delete(client, actor, uid):
    """[functional] The owner can read, update and delete their document."""
    who = uid("u")
    doc = _create(client, actor, who).json()
    assert client.get(f"/documents/{doc['id']}", headers=actor(who, "user")).status_code == 200
    assert client.patch(f"/documents/{doc['id']}", json={"title": "New"}, headers=actor(who, "user")).json()["title"] == "New"
    assert client.delete(f"/documents/{doc['id']}", headers=actor(who, "user")).status_code == 204


def test_admin_sees_and_reads_everything(client, actor, uid):
    """[functional] An admin's list includes other users' documents and the admin can read them."""
    doc = _create(client, actor, uid("u")).json()
    ids = [d["id"] for d in client.get("/documents", headers=actor(uid("adm"), "admin")).json()]
    assert doc["id"] in ids
    assert client.get(f"/documents/{doc['id']}", headers=actor(uid("adm"), "admin")).status_code == 200


def test_list_shows_only_own_documents(client, actor, uid):
    """[safety] A user's list contains their documents and none of another user's."""
    alice, bob = uid("alice"), uid("bob")
    mine = _create(client, actor, alice).json()
    theirs = _create(client, actor, bob).json()
    listed = client.get("/documents", headers=actor(alice, "user")).json()
    ids = [d["id"] for d in listed]
    assert mine["id"] in ids and theirs["id"] not in ids
    assert all(d["owner_id"] == alice for d in listed)


def test_query_parameters_cannot_widen_the_list(client, actor, uid):
    """[safety] ?owner_id=, ?all=true or ?role=admin never reveal another user's documents."""
    alice, bob = uid("alice"), uid("bob")
    theirs = _create(client, actor, bob).json()
    _create(client, actor, alice)
    for params in ({"owner_id": bob}, {"all": "true"}, {"role": "admin"}):
        r = client.get("/documents", params=params, headers=actor(alice, "user"))
        assert r.status_code in (200, 422)
        if r.status_code == 200:
            assert theirs["id"] not in [d["id"] for d in r.json()], params


def test_reading_another_users_document_is_404(client, actor, uid):
    """[safety] Reading another user's document returns 404, same as a missing one."""
    doc = _create(client, actor, uid("bob")).json()
    assert client.get(f"/documents/{doc['id']}", headers=actor(uid("alice"), "user")).status_code == 404


def test_updating_another_users_document_is_404_and_unchanged(client, actor, uid):
    """[safety] PATCH on another user's document is 404 and the document is unchanged."""
    bob = uid("bob")
    doc = _create(client, actor, bob).json()
    r = client.patch(f"/documents/{doc['id']}", json={"body": "hacked"}, headers=actor(uid("alice"), "user"))
    assert r.status_code == 404
    assert client.get(f"/documents/{doc['id']}", headers=actor(bob, "user")).json()["body"] == "secret plans"


def test_deleting_another_users_document_is_404_and_it_survives(client, actor, uid):
    """[safety] DELETE on another user's document is 404 and the document still exists."""
    bob = uid("bob")
    doc = _create(client, actor, bob).json()
    assert client.delete(f"/documents/{doc['id']}", headers=actor(uid("alice"), "user")).status_code == 404
    assert client.get(f"/documents/{doc['id']}", headers=actor(bob, "user")).status_code == 200


def test_owner_cannot_be_supplied_or_changed(client, actor, uid):
    """[safety] owner_id in create or update bodies is rejected with 422."""
    who = uid("u")
    assert _create(client, actor, who, owner_id=uid("other")).status_code == 422
    doc = _create(client, actor, who).json()
    r = client.patch(f"/documents/{doc['id']}", json={"owner_id": uid("other")}, headers=actor(who, "user"))
    assert r.status_code == 422


def test_admin_can_delete_any_document(client, actor, uid):
    """[functional] An admin can delete another user's document."""
    bob = uid("bob")
    doc = _create(client, actor, bob).json()
    assert client.delete(f"/documents/{doc['id']}", headers=actor(uid("adm"), "admin")).status_code == 204
    assert client.get(f"/documents/{doc['id']}", headers=actor(bob, "user")).status_code == 404


def test_missing_partial_or_unknown_identity_is_403(client, actor, uid):
    """[safety] Missing, partial or unknown-role identity headers are exactly 403 on every route and change nothing."""
    who = uid("u")
    doc = _create(client, actor, who).json()
    for headers in ({}, {"x-actor-id": who}, {"x-actor-role": "user"}, actor(who, "superuser")):
        assert client.get("/documents", headers=headers).status_code == 403, headers
        assert client.post("/documents", json={"title": "T", "body": "B"}, headers=headers).status_code == 403, headers
        assert client.get(f"/documents/{doc['id']}", headers=headers).status_code == 403, headers
        assert client.patch(f"/documents/{doc['id']}", json={"title": "X"}, headers=headers).status_code == 403, headers
        assert client.delete(f"/documents/{doc['id']}", headers=headers).status_code == 403, headers
    mine = client.get("/documents", headers=actor(who, "user")).json()
    assert [d["id"] for d in mine] == [doc["id"]] and mine[0]["title"] == "Notes"


def test_blank_title_is_422(client, actor, uid):
    """[safety] A blank or empty title is rejected with 422 on create and on update, and the document is unchanged."""
    who = uid("u")
    assert _create(client, actor, who, title="  ").status_code == 422
    assert _create(client, actor, who, title="").status_code == 422
    doc = _create(client, actor, who).json()
    for title in ("  ", ""):
        r = client.patch(f"/documents/{doc['id']}", json={"title": title}, headers=actor(who, "user"))
        assert r.status_code == 422, repr(title)
    assert client.get(f"/documents/{doc['id']}", headers=actor(who, "user")).json()["title"] == "Notes"


def test_unknown_document_is_404_and_a_foreign_one_looks_identical(client, actor, uid):
    """[safety] An unknown document id is 404 for users and admins, and another user's document answers like a missing one."""
    alice, bob = uid("alice"), uid("bob")
    doc = _create(client, actor, bob).json()
    missing = uid("nope")
    for who, role in ((alice, "user"), (uid("adm"), "admin")):
        headers = actor(who, role)
        assert client.get(f"/documents/{missing}", headers=headers).status_code == 404
        assert client.patch(f"/documents/{missing}", json={"title": "x"}, headers=headers).status_code == 404
        assert client.delete(f"/documents/{missing}", headers=headers).status_code == 404
    foreign = client.get(f"/documents/{doc['id']}", headers=actor(alice, "user"))
    unknown = client.get(f"/documents/{missing}", headers=actor(alice, "user"))
    assert foreign.status_code == unknown.status_code == 404
    assert foreign.text.replace(doc["id"], "<id>") == unknown.text.replace(missing, "<id>")
    assert "secret plans" not in foreign.text and bob not in foreign.text


def test_admin_can_update_any_document_without_taking_ownership(client, actor, uid):
    """[functional] An admin can update another user's document; the owner stays the original user."""
    bob = uid("bob")
    doc = _create(client, actor, bob).json()
    r = client.patch(f"/documents/{doc['id']}", json={"body": "edited by admin"}, headers=actor(uid("adm"), "admin"))
    assert r.status_code == 200 and r.json()["body"] == "edited by admin" and r.json()["owner_id"] == bob
    assert client.get(f"/documents/{doc['id']}", headers=actor(bob, "user")).json()["body"] == "edited by admin"


def test_admin_owner_is_the_caller_and_cannot_be_changed(client, actor, uid):
    """[safety] An admin's own document is owned by the admin; an admin cannot supply or change an owner."""
    adm, bob = uid("adm"), uid("bob")
    mine = _create(client, actor, adm, role="admin")
    assert mine.status_code == 201 and mine.json()["owner_id"] == adm
    assert _create(client, actor, adm, role="admin", owner_id=bob).status_code == 422
    theirs = _create(client, actor, bob).json()
    r = client.patch(f"/documents/{theirs['id']}", json={"owner_id": adm}, headers=actor(adm, "admin"))
    assert r.status_code == 422
    assert client.get(f"/documents/{theirs['id']}", headers=actor(bob, "user")).json()["owner_id"] == bob
    assert client.get(f"/documents/{mine.json()['id']}", headers=actor(bob, "user")).status_code == 404


def test_patch_updates_only_the_supplied_fields(client, actor, uid):
    """[functional] Updating only the title keeps the body, and updating only the body keeps the title."""
    who = uid("u")
    doc = _create(client, actor, who, title="Original", body="Original body").json()
    headers = actor(who, "user")
    first = client.patch(f"/documents/{doc['id']}", json={"title": "Changed"}, headers=headers).json()
    assert first["title"] == "Changed" and first["body"] == "Original body"
    second = client.patch(f"/documents/{doc['id']}", json={"body": "Changed body"}, headers=headers).json()
    assert second["title"] == "Changed" and second["body"] == "Changed body"


def test_response_fields_match_the_interface(client, actor, uid):
    """[functional] Create, read, update and list responses carry id, owner_id, title and body."""
    who = uid("u")
    headers = actor(who, "user")
    fields = {"id", "owner_id", "title", "body"}
    created = client.post("/documents", json={"title": "T", "body": "B"}, headers=headers)
    assert created.status_code == 201 and fields <= set(created.json())
    doc_id = created.json()["id"]
    assert fields <= set(client.get(f"/documents/{doc_id}", headers=headers).json())
    patched = client.patch(f"/documents/{doc_id}", json={"body": "B2"}, headers=headers)
    assert patched.status_code == 200 and fields <= set(patched.json())
    listed = client.get("/documents", headers=headers).json()
    assert listed and all(fields <= set(item) for item in listed)


def test_query_parameters_cannot_widen_a_single_read(client, actor, uid):
    """[safety] ?owner_id=, ?all=true or ?role=admin do not let a user read or delete another user's document."""
    alice, bob = uid("alice"), uid("bob")
    doc = _create(client, actor, bob).json()
    for params in ({"owner_id": alice}, {"all": "true"}, {"role": "admin"}):
        headers = actor(alice, "user")
        assert client.get(f"/documents/{doc['id']}", params=params, headers=headers).status_code in (404, 422), params
        assert client.delete(f"/documents/{doc['id']}", params=params, headers=headers).status_code in (404, 422), params
    assert client.get(f"/documents/{doc['id']}", headers=actor(bob, "user")).status_code == 200


def test_deleted_document_is_gone_for_everyone(client, actor, uid):
    """[functional] After the owner deletes a document it is 404 to read or delete again and missing from every list."""
    who = uid("u")
    doc = _create(client, actor, who).json()
    assert client.delete(f"/documents/{doc['id']}", headers=actor(who, "user")).status_code == 204
    for headers in (actor(who, "user"), actor(uid("adm"), "admin")):
        assert client.get(f"/documents/{doc['id']}", headers=headers).status_code == 404
        assert client.delete(f"/documents/{doc['id']}", headers=headers).status_code == 404
        assert doc["id"] not in [d["id"] for d in client.get("/documents", headers=headers).json()]


def test_missing_required_fields_are_422(client, actor, uid):
    """[safety] Creating a document without a title or without a body is rejected with 422."""
    headers = actor(uid("u"), "user")
    assert client.post("/documents", json={"body": "B"}, headers=headers).status_code == 422
    assert client.post("/documents", json={"title": "T"}, headers=headers).status_code == 422
