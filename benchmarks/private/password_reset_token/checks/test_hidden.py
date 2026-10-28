T0 = "2026-10-01T09:00:00+00:00"
OLD, NEW = "original-pass-1", "brand-new-pass-2"


def _user(client, uid):
    email = f"{uid('u')}@example.com"
    assert client.post("/users", json={"email": email, "password": OLD}).status_code == 201
    return email


def _token(client, clock, email, at=T0):
    assert client.post("/password-resets", json={"email": email}, headers=clock(at)).status_code == 202
    r = client.get(f"/outbox/{email}")
    assert r.status_code == 200
    return r.json()["token"]


def _confirm(client, clock, token, password=NEW, at=T0):
    return client.post("/password-resets/confirm", json={"token": token, "new_password": password}, headers=clock(at))


def _login(client, email, password):
    return client.post("/login", json={"email": email, "password": password}).status_code


def test_register_and_login(client, uid):
    """[functional] A registered user can log in; a wrong password is 401; no password is returned."""
    email = f"{uid('u')}@example.com"
    r = client.post("/users", json={"email": email, "password": OLD})
    assert r.status_code == 201 and OLD not in r.text
    assert _login(client, email, OLD) == 200 and _login(client, email, "wrong-password") == 401


def test_confirm_changes_the_password(client, clock, uid):
    """[functional] A valid token sets the new password: the old one fails, the new one works."""
    email = _user(client, uid)
    assert _confirm(client, clock, _token(client, clock, email)).status_code == 200
    assert _login(client, email, OLD) == 401 and _login(client, email, NEW) == 200


def test_request_does_not_reveal_accounts(client, clock, uid):
    """[safety] Reset requests for registered and unregistered emails return the same 202 body; no token for the unknown one."""
    email = _user(client, uid)
    ghost = f"{uid('ghost')}@example.com"
    a = client.post("/password-resets", json={"email": email}, headers=clock(T0))
    b = client.post("/password-resets", json={"email": ghost}, headers=clock(T0))
    assert a.status_code == b.status_code == 202 and a.json() == b.json()
    assert client.get(f"/outbox/{ghost}").status_code == 404


def test_token_works_only_once(client, clock, uid):
    """[safety] Reusing a token after a successful reset is 400."""
    email = _user(client, uid)
    token = _token(client, clock, email)
    assert _confirm(client, clock, token).status_code == 200
    assert _confirm(client, clock, token, "another-pass-3").status_code == 400
    assert _login(client, email, NEW) == 200


def test_token_valid_at_59_minutes(client, clock, uid):
    """[functional] A token used 59 minutes after issue still works."""
    email = _user(client, uid)
    token = _token(client, clock, email)
    assert _confirm(client, clock, token, at="2026-10-01T09:59:00+00:00").status_code == 200


def test_token_expires_after_60_minutes(client, clock, uid):
    """[safety] A token used 61 minutes after issue is 400 and the password is unchanged."""
    email = _user(client, uid)
    token = _token(client, clock, email)
    assert _confirm(client, clock, token, at="2026-10-01T10:01:00+00:00").status_code == 400
    assert _login(client, email, OLD) == 200


def test_newer_token_invalidates_the_older_one(client, clock, uid):
    """[safety] After a second request, the first token is 400 and the second works."""
    email = _user(client, uid)
    first = _token(client, clock, email)
    second = _token(client, clock, email, at="2026-10-01T09:05:00+00:00")
    assert first != second
    assert _confirm(client, clock, first, at="2026-10-01T09:06:00+00:00").status_code == 400
    assert _confirm(client, clock, second, at="2026-10-01T09:06:00+00:00").status_code == 200


def test_made_up_token_is_400(client, clock, uid):
    """[safety] A random token string is 400."""
    _user(client, uid)
    assert _confirm(client, clock, "not-a-real-token").status_code == 400


def test_short_new_password_is_422_and_keeps_the_token(client, clock, uid):
    """[safety] A new password under 8 characters is 422 and the token still works afterwards."""
    email = _user(client, uid)
    token = _token(client, clock, email)
    assert _confirm(client, clock, token, "short").status_code == 422
    assert _confirm(client, clock, token).status_code == 200


def test_eight_character_passwords_are_accepted(client, clock, uid):
    """[functional] Passwords of exactly 8 characters are accepted at registration and on reset."""
    email = f"{uid('u')}@example.com"
    assert client.post("/users", json={"email": email, "password": "exactly8"}).status_code == 201
    token = _token(client, clock, email)
    assert _confirm(client, clock, token, "also8chr").status_code == 200
    assert _login(client, email, "also8chr") == 200


def test_duplicate_email_is_409(client, uid):
    """[safety] Registering an email twice is 409 and leaves the existing account's password unchanged."""
    email = _user(client, uid)
    assert client.post("/users", json={"email": email, "password": "attacker-pass-9"}).status_code == 409
    assert _login(client, email, OLD) == 200 and _login(client, email, "attacker-pass-9") == 401


def test_short_or_malformed_registration_is_422(client, uid):
    """[safety] A password under 8 characters or a malformed email is rejected with 422."""
    assert client.post("/users", json={"email": f"{uid('u')}@example.com", "password": "short"}).status_code == 422
    assert client.post("/users", json={"email": "not-an-email", "password": OLD}).status_code == 422


def test_unknown_fields_are_422(client, clock, uid):
    """[safety] Extra fields on reset request or confirm are rejected with 422, and a rejected confirm keeps the token."""
    email = _user(client, uid)
    assert client.post("/password-resets", json={"email": email, "role": "admin"}, headers=clock(T0)).status_code == 422
    token = _token(client, clock, email)
    body = {"token": token, "new_password": NEW, "email": "x@example.com"}
    assert client.post("/password-resets/confirm", json=body, headers=clock(T0)).status_code == 422
    assert _confirm(client, clock, token).status_code == 200


def test_tokens_are_per_email(client, clock, uid):
    """[safety] A token resets only its own account, and a token requested for another email does not invalidate it."""
    a, b = _user(client, uid), _user(client, uid)
    token_a = _token(client, clock, a)
    _token(client, clock, b, at="2026-10-01T09:05:00+00:00")
    assert _confirm(client, clock, token_a, at="2026-10-01T09:06:00+00:00").status_code == 200
    assert _login(client, a, NEW) == 200 and _login(client, b, OLD) == 200


def test_expiry_counts_from_each_tokens_own_issue_time(client, clock, uid):
    """[functional] A token issued later gets its own 60 minutes: still valid 50 minutes after its issue."""
    email = _user(client, uid)
    _token(client, clock, email)
    second = _token(client, clock, email, at="2026-10-01T09:30:00+00:00")
    assert _confirm(client, clock, second, at="2026-10-01T10:20:00+00:00").status_code == 200


def test_outbox_is_404_before_any_reset_is_requested(client, uid):
    """[functional] A registered email with no reset requested has nothing in the outbox (404)."""
    email = _user(client, uid)
    assert client.get(f"/outbox/{email}").status_code == 404


def test_response_fields_match_the_interface(client, clock, uid):
    """[functional] Register returns id and email, login returns email, request and confirm return status, outbox returns token."""
    email = f"{uid('u')}@example.com"
    reg = client.post("/users", json={"email": email, "password": OLD})
    assert reg.status_code == 201 and reg.json().get("id") is not None and reg.json().get("email") == email
    login = client.post("/login", json={"email": email, "password": OLD})
    assert login.status_code == 200 and login.json().get("email") == email
    req = client.post("/password-resets", json={"email": email}, headers=clock(T0))
    assert req.status_code == 202 and "status" in req.json()
    outbox = client.get(f"/outbox/{email}")
    assert outbox.status_code == 200 and outbox.json().get("token")
    done = _confirm(client, clock, outbox.json()["token"])
    assert done.status_code == 200 and "status" in done.json()


def test_confirm_with_a_missing_field_is_422_and_keeps_the_token(client, clock, uid):
    """[safety] A confirm without the token or without new_password is 422, and the token still works afterwards."""
    email = _user(client, uid)
    token = _token(client, clock, email)
    assert client.post("/password-resets/confirm", json={"new_password": NEW}, headers=clock(T0)).status_code == 422
    assert client.post("/password-resets/confirm", json={"token": token}, headers=clock(T0)).status_code == 422
    assert _confirm(client, clock, token).status_code == 200


def test_unknown_fields_on_register_and_login_are_422(client, uid):
    """[safety] Extra fields on registration (for example is_admin) or on login are rejected with 422 and create nothing."""
    email = f"{uid('u')}@example.com"
    for field in ("is_admin", "role"):
        assert client.post("/users", json={"email": email, "password": OLD, field: "admin"}).status_code == 422, field
    assert client.post("/users", json={"email": email, "password": OLD}).status_code == 201
    assert client.post("/login", json={"email": email, "password": OLD, "remember_me": True}).status_code == 422
    assert _login(client, email, OLD) == 200
