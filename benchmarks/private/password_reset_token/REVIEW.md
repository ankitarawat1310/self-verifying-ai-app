# Manual review: password_reset_token



test_register_and_login ........................................ OK  
test_confirm_changes_the_password .............................. OK  
test_request_does_not_reveal_accounts .......................... OK  
test_token_works_only_once ..................................... OK  
test_token_valid_at_59_minutes ................................. OK  
test_token_expires_after_60_minutes ............................ OK  
test_newer_token_invalidates_the_older_one ..................... OK  
test_made_up_token_is_400 ...................................... OK  
test_short_new_password_is_422_and_keeps_the_token ............. OK  
test_eight_character_passwords_are_accepted .................... OK  
test_duplicate_email_is_409 .................................... Not stated (fixed by clarifying the prompt)  
test_short_or_malformed_registration_is_422 .................... OK  
test_unknown_fields_are_422 .................................... OK (code covered less than its description; fixed)  
test_tokens_are_per_email ...................................... OK (added in review)  
test_expiry_counts_from_each_tokens_own_issue_time ............. OK (added in review)  
test_outbox_is_404_before_any_reset_is_requested ............... OK (added in review)  
test_response_fields_match_the_interface ....................... OK (added in review)  
test_confirm_with_a_missing_field_is_422_and_keeps_the_token ... OK (added in review)  
test_unknown_fields_on_register_and_login_are_422 .............. OK (added in review)  

Changes made after review:

- Not stated: the prompt never said emails are unique or that a duplicate registration is rejected; only the shared conflict: 409 convention existed. The public prompt now says 'Emails are unique: registering an email that is already registered returns 409 and leaves the existing account unchanged.' The check now also proves the existing password still works and the second registration's password does not.
- Description versus code: test_unknown_fields_are_422 claimed to cover the reset request and confirm, but only exercised confirm. It now covers both, and also proves a confirm rejected for validation does not use up the token. The old confirm call also omitted the x-clock-now header, so it silently depended on the machine's real clock; every time-sensitive call now sends the test clock.
- Mutant-driven: the first mutant pass left one survivor (extra='forbid' removed from the login model), which showed no check sent an undeclared field to registration or login. Added test_unknown_fields_on_register_and_login_are_422 (is_admin and role on registration, an extra field on login, and the rejected registrations must create no account). The re-run kills all 12 sampled mutants.
- Added: a token resets only its own account, and a token requested for another email does not invalidate it.
- Added: expiry is counted from each token's own issue time (a second token issued at 09:30 still works at 10:20).
- Added: the outbox is 404 for a registered email before any reset is requested.
- Added: declared response fields for register, login, reset request, outbox and confirm.
- Added: a confirm without token or without new_password is 422 and does not use up the token.

Remaining lower-priority coverage:

- The exact 60:00 expiry instant is not tested. 'Expires 60 minutes after it was issued' does not say whether the last instant is valid, so the checks use 59 and 61 minutes.
- Not stated, not tested: logging in with an unregistered email (the interface only lists wrong_credentials: 401), a malformed email on the reset request (no format is declared for it), and case sensitivity of emails.
- Unclear: 'Passwords are never returned' is checked for registration only; a default FastAPI 422 body echoes the submitted input, so it is not enforced on error responses.

Validation: reference 19/19, stub 0/19, deterministic, 12 automatic bugs caught (all 12 sampled were killed) + security bugs 3/3.


