# Manual review: login_lockout



test_register_never_returns_the_password .................. OK  
test_correct_login_returns_a_token ........................ OK  
test_wrong_password_and_unknown_user_are_401 .............. OK  
test_four_failures_do_not_lock ............................ OK  
test_fifth_failure_locks_even_the_correct_password ........ OK  
test_lock_still_holds_just_before_15_minutes .............. OK  
test_lock_expires_after_15_minutes ........................ OK  
test_success_resets_the_failure_count ..................... OK  
test_lock_is_per_username ................................. OK  
test_duplicate_username_is_409 ............................ OK  
test_short_password_is_422 ................................ OK  
test_unknown_fields_are_422 ............................... OK  
test_response_fields_match_the_interface .................. OK (added in review)  
test_wrong_password_during_the_lock_is_423 ................ OK (added in review)  
test_lock_is_measured_from_the_fifth_failure .............. OK (added in review)  
test_password_of_exactly_8_characters_is_accepted ......... OK (added in review)  
test_empty_or_missing_registration_fields_are_422 ......... OK (added in review)  
test_login_with_a_missing_field_is_422 .................... OK (added in review)  
test_login_with_an_unknown_field_is_422 ................... OK (added in review)  
test_duplicate_registration_keeps_the_original_password ... OK (added in review)  
test_one_character_username_is_accepted ................... OK (added in review)  

Changes made after review:

- The 12 existing checks all trace to the prompt or interface; none was changed. The x-clock-now boundary is probed on both sides (14:59 still 423, 15:01 works again).
- Added the rule that every login attempt during the lock is 423, including a wrong password.
- Added a check that the 15 minutes start at the fifth failure, not the first (4 failures at 09:00, the fifth at 09:10: still 423 at 09:16, allowed at 09:25:01).
- Added the exact boundaries of the declared field rules: a password of exactly 8 characters and a username of exactly 1 character are accepted.
- Added empty/missing registration fields, missing login fields and an undeclared login field (all 422).
- Added a duplicate registration (409) that must leave the original password working and the attacker's password rejected.
- Added assertions for the declared response fields (id, username, token).

Remaining lower-priority coverage:

- The exact 15:00 lock-expiry instant is not tested: the prompt does not say whether the lock ends at or after 15 minutes, so the checks stay 1 second away from it (two boundary-comparison mutants survive for this reason).
- Unclear: 'passwords are never returned in any response' is checked for registration and login responses only. A default FastAPI 422 body echoes the submitted input, including the password (the reference app does too), so a literal every-response check is not enforced.
- Not stated, not tested: whether attempts made during a lock extend it, and whether the failure count restarts when a lock expires.
- Whitespace-only usernames (the interface only requires min_length 1).

Validation: reference 21/21, stub 0/21, deterministic, 8 automatic bugs caught + security bugs 3/3. Surviving automatic mutants: 2 exact-boundary comparisons and 2 equivalent validation mutants (the not-blank validator also rejects an empty username).


