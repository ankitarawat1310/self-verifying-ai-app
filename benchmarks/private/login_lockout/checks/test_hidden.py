T0 = "2026-10-01T09:00:00+00:00"
PW = "correct-horse-1"


def _register(client, uid):
    name = uid("user")
    assert client.post("/users", json={"username": name, "password": PW}).status_code == 201
    return name


def _login(client, clock, name, password=PW, at=T0):
    return client.post("/login", json={"username": name, "password": password}, headers=clock(at))


def _fail(client, clock, name, times, at=T0):
    return [_login(client, clock, name, "wrong-password", at).status_code for _ in range(times)]


def test_register_never_returns_the_password(client, uid):
    """[safety] Registration is 201 and the response does not contain the password."""
    r = client.post("/users", json={"username": uid("u"), "password": PW})
    assert r.status_code == 201 and "password" not in r.json() and PW not in r.text


def test_correct_login_returns_a_token(client, clock, uid):
    """[functional] Correct credentials return 200 with a token and no password."""
    name = _register(client, uid)
    r = _login(client, clock, name)
    assert r.status_code == 200 and r.json().get("token") and PW not in r.text


def test_wrong_password_and_unknown_user_are_401(client, clock, uid):
    """[safety] A wrong password and an unknown username both return 401."""
    name = _register(client, uid)
    assert _login(client, clock, name, "nope-nope-nope").status_code == 401
    assert _login(client, clock, uid("ghost")).status_code == 401


def test_four_failures_do_not_lock(client, clock, uid):
    """[functional] After 4 failures the correct password still works."""
    name = _register(client, uid)
    assert _fail(client, clock, name, 4) == [401] * 4
    assert _login(client, clock, name).status_code == 200


def test_fifth_failure_locks_even_the_correct_password(client, clock, uid):
    """[safety] After 5 consecutive failures, the correct password returns 423."""
    name = _register(client, uid)
    assert _fail(client, clock, name, 5) == [401] * 5
    assert _login(client, clock, name).status_code == 423


def test_lock_still_holds_just_before_15_minutes(client, clock, uid):
    """[safety] 14 minutes 59 seconds after locking, login is still 423."""
    name = _register(client, uid)
    _fail(client, clock, name, 5)
    assert _login(client, clock, name, at="2026-10-01T09:14:59+00:00").status_code == 423


def test_lock_expires_after_15_minutes(client, clock, uid):
    """[functional] 15 minutes after locking, the correct password works again."""
    name = _register(client, uid)
    _fail(client, clock, name, 5)
    assert _login(client, clock, name, at="2026-10-01T09:15:01+00:00").status_code == 200


def test_success_resets_the_failure_count(client, clock, uid):
    """[functional] 4 failures, a success, then 4 more failures: still not locked."""
    name = _register(client, uid)
    _fail(client, clock, name, 4)
    assert _login(client, clock, name).status_code == 200
    _fail(client, clock, name, 4)
    assert _login(client, clock, name).status_code == 200


def test_lock_is_per_username(client, clock, uid):
    """[safety] Locking one account does not affect another."""
    locked, other = _register(client, uid), _register(client, uid)
    _fail(client, clock, locked, 5)
    assert _login(client, clock, other).status_code == 200


def test_duplicate_username_is_409(client, uid):
    """[safety] Registering an existing username is 409."""
    name = _register(client, uid)
    assert client.post("/users", json={"username": name, "password": PW}).status_code == 409


def test_short_password_is_422(client, uid):
    """[safety] A password shorter than 8 characters is rejected with 422."""
    assert client.post("/users", json={"username": uid("u"), "password": "short7!"}).status_code == 422


def test_unknown_fields_are_422(client, uid):
    """[safety] Extra registration fields such as role or is_admin are rejected with 422."""
    for field in ("role", "is_admin"):
        body = {"username": uid("u"), "password": PW, field: "admin"}
        assert client.post("/users", json=body).status_code == 422, field


def test_response_fields_match_the_interface(client, clock, uid):
    """[functional] Registration returns id and username; login returns username and token."""
    name = uid("u")
    reg = client.post("/users", json={"username": name, "password": PW})
    assert reg.status_code == 201
    assert reg.json().get("id") is not None and reg.json().get("username") == name
    login = _login(client, clock, name)
    assert login.status_code == 200
    assert login.json().get("username") == name and login.json().get("token")


def test_wrong_password_during_the_lock_is_423(client, clock, uid):
    """[safety] Every login attempt during the lock returns 423, including one with a wrong password."""
    name = _register(client, uid)
    _fail(client, clock, name, 5)
    assert _login(client, clock, name, "wrong-password", at="2026-10-01T09:05:00+00:00").status_code == 423


def test_lock_is_measured_from_the_fifth_failure(client, clock, uid):
    """[safety] The 15 minutes start at the fifth failure, not the first: still locked 6 minutes into the lock."""
    name = _register(client, uid)
    _fail(client, clock, name, 4, at="2026-10-01T09:00:00+00:00")
    _fail(client, clock, name, 1, at="2026-10-01T09:10:00+00:00")
    assert _login(client, clock, name, at="2026-10-01T09:16:00+00:00").status_code == 423
    assert _login(client, clock, name, at="2026-10-01T09:25:01+00:00").status_code == 200


def test_password_of_exactly_8_characters_is_accepted(client, uid):
    """[functional] A password of exactly 8 characters is accepted with 201."""
    assert client.post("/users", json={"username": uid("u"), "password": "12345678"}).status_code == 201


def test_empty_or_missing_registration_fields_are_422(client, uid):
    """[safety] Registration with an empty username, or a missing username or password, is rejected with 422."""
    assert client.post("/users", json={"username": "", "password": PW}).status_code == 422
    assert client.post("/users", json={"password": PW}).status_code == 422
    assert client.post("/users", json={"username": uid("u")}).status_code == 422


def test_login_with_a_missing_field_is_422(client, clock, uid):
    """[functional] A login body missing the username or the password is rejected with 422."""
    name = _register(client, uid)
    assert client.post("/login", json={"username": name}, headers=clock(T0)).status_code == 422
    assert client.post("/login", json={"password": PW}, headers=clock(T0)).status_code == 422


def test_login_with_an_unknown_field_is_422(client, clock, uid):
    """[functional] A login body with an undeclared field is rejected with 422."""
    name = _register(client, uid)
    body = {"username": name, "password": PW, "remember_me": True}
    assert client.post("/login", json=body, headers=clock(T0)).status_code == 422


def test_duplicate_registration_keeps_the_original_password(client, clock, uid):
    """[safety] A rejected duplicate registration does not change the existing account's password."""
    name = _register(client, uid)
    assert client.post("/users", json={"username": name, "password": "attacker-pass-9"}).status_code == 409
    assert _login(client, clock, name).status_code == 200
    assert _login(client, clock, name, "attacker-pass-9").status_code == 401


def test_one_character_username_is_accepted(client):
    """[functional] A username of exactly 1 character is accepted with 201."""
    assert client.post("/users", json={"username": "z", "password": PW}).status_code == 201
