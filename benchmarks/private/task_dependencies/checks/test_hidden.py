def _task(client, title="t", deps=None):
    body = {"title": title}
    if deps is not None:
        body["depends_on"] = deps
    r = client.post("/tasks", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _complete(client, tid):
    return client.post(f"/tasks/{tid}/complete")


def _depend(client, tid, on):
    return client.post(f"/tasks/{tid}/dependencies", json={"task_id": on})


def test_new_task_is_todo(client):
    """[functional] A new task is 201 with status todo and its dependency list."""
    a = _task(client)
    r = client.post("/tasks", json={"title": "b", "depends_on": [a]})
    assert r.status_code == 201 and r.json()["status"] == "todo" and r.json()["depends_on"] == [a]


def test_task_without_dependencies_can_complete(client):
    """[functional] A task with no dependencies completes: status done."""
    r = _complete(client, _task(client))
    assert r.status_code == 200 and r.json()["status"] == "done"


def test_blocked_until_dependency_is_done(client):
    """[safety] Completing a task whose dependency is todo is 409; after the dependency is done it succeeds."""
    a = _task(client)
    b = _task(client, deps=[a])
    assert _complete(client, b).status_code == 409
    assert client.get(f"/tasks/{b}").json()["status"] == "todo"
    assert _complete(client, a).status_code == 200
    assert _complete(client, b).status_code == 200


def test_chain_must_complete_in_order(client):
    """[safety] In a chain a <- b <- c, c cannot complete before b, even if a is done."""
    a = _task(client)
    b = _task(client, deps=[a])
    c = _task(client, deps=[b])
    assert _complete(client, a).status_code == 200
    assert _complete(client, c).status_code == 409
    assert _complete(client, b).status_code == 200
    assert _complete(client, c).status_code == 200


def test_all_dependencies_are_required(client):
    """[safety] With two dependencies, finishing only one still blocks completion."""
    a, b = _task(client), _task(client)
    c = _task(client, deps=[a, b])
    _complete(client, a)
    assert _complete(client, c).status_code == 409


def test_unknown_dependency_is_422(client):
    """[safety] Depending on a task id that does not exist is 422 (on create and on add)."""
    assert client.post("/tasks", json={"title": "x", "depends_on": ["does-not-exist"]}).status_code == 422
    assert _depend(client, _task(client), "does-not-exist").status_code == 422


def test_self_dependency_is_422(client):
    """[safety] A task cannot depend on itself."""
    a = _task(client)
    assert _depend(client, a, a).status_code == 422


def test_two_task_cycle_is_409(client):
    """[safety] If b depends on a, making a depend on b is 409."""
    a = _task(client)
    b = _task(client, deps=[a])
    assert _depend(client, a, b).status_code == 409
    assert client.get(f"/tasks/{a}").json()["depends_on"] == []


def test_longer_cycle_is_409(client):
    """[safety] With c -> b -> a, making a depend on c is 409."""
    a = _task(client)
    b = _task(client, deps=[a])
    c = _task(client, deps=[b])
    assert _depend(client, a, c).status_code == 409


def test_completing_twice_is_409(client):
    """[safety] Completing a done task again is 409."""
    a = _task(client)
    assert _complete(client, a).status_code == 200
    assert _complete(client, a).status_code == 409


def test_no_new_dependencies_on_a_done_task(client):
    """[safety] Adding a dependency to a done task is 409 and its dependency list is unchanged."""
    a, other = _task(client), _task(client)
    _complete(client, a)
    assert _depend(client, a, other).status_code == 409
    assert client.get(f"/tasks/{a}").json()["depends_on"] == []


def test_adding_a_valid_dependency_and_unknown_task(client):
    """[functional] Adding a dependency on another task succeeds; unknown task ids are 404."""
    a, b = _task(client), _task(client)
    r = _depend(client, b, a)
    assert r.status_code == 200 and a in r.json()["depends_on"]
    assert client.get("/tasks/nope").status_code == 404
    assert _complete(client, "nope").status_code == 404


def test_status_cannot_be_supplied(client):
    """[safety] Caller-supplied status on create is rejected with 422."""
    assert client.post("/tasks", json={"title": "x", "status": "done"}).status_code == 422


def test_added_dependencies_block_completion(client):
    """[safety] A dependency added after creation blocks completion until that dependency is done."""
    a, b = _task(client), _task(client)
    assert _depend(client, b, a).status_code == 200
    assert _complete(client, b).status_code == 409
    assert client.get(f"/tasks/{b}").json()["status"] == "todo"
    assert _complete(client, a).status_code == 200
    assert _complete(client, b).status_code == 200


def test_diamond_dependencies_are_not_cycles(client):
    """[functional] A diamond (b and c depend on a, d depends on b and c) is accepted; closing it back onto a is 409."""
    a, b, c, d = (_task(client) for _ in range(4))
    for task, on in ((b, a), (c, a), (d, b), (d, c)):
        assert _depend(client, task, on).status_code == 200, (task, on)
    assert sorted(client.get(f"/tasks/{d}").json()["depends_on"]) == sorted([b, c])
    assert _depend(client, a, d).status_code == 409


def test_adding_a_dependency_to_an_unknown_task_is_404(client):
    """[functional] Adding a dependency to a task id that does not exist is 404."""
    assert _depend(client, "no-such-task", _task(client)).status_code == 404


def test_unknown_and_self_dependencies_change_nothing(client):
    """[safety] A rejected unknown or self dependency leaves the task's dependency list unchanged."""
    a = _task(client)
    assert _depend(client, a, "does-not-exist").status_code == 422
    assert _depend(client, a, a).status_code == 422
    assert client.get(f"/tasks/{a}").json()["depends_on"] == []


def test_response_fields_match_the_interface(client):
    """[functional] Create, read, add-dependency and complete responses carry id, title, depends_on and status."""
    fields = {"id", "title", "depends_on", "status"}
    created = client.post("/tasks", json={"title": "Alpha"})
    assert created.status_code == 201 and fields <= set(created.json())
    assert created.json()["title"] == "Alpha" and created.json()["depends_on"] == []
    a, b = created.json()["id"], _task(client)
    assert fields <= set(client.get(f"/tasks/{a}").json())
    added = _depend(client, b, a)
    assert added.status_code == 200 and fields <= set(added.json())
    done = _complete(client, a)
    assert done.status_code == 200 and fields <= set(done.json())


def test_empty_or_missing_title_and_bad_depends_on_are_422(client):
    """[safety] An empty or missing title, or a depends_on that is not a list, is rejected with 422."""
    assert client.post("/tasks", json={"title": ""}).status_code == 422
    assert client.post("/tasks", json={}).status_code == 422
    assert client.post("/tasks", json={"title": "x", "depends_on": "not-a-list"}).status_code == 422


def test_add_dependency_body_is_validated(client):
    """[safety] Adding a dependency without task_id, or with an extra field, is rejected with 422 and changes nothing."""
    a, b = _task(client), _task(client)
    assert client.post(f"/tasks/{b}/dependencies", json={}).status_code == 422
    assert client.post(f"/tasks/{b}/dependencies", json={"task_id": a, "note": "x"}).status_code == 422
    assert client.get(f"/tasks/{b}").json()["depends_on"] == []
