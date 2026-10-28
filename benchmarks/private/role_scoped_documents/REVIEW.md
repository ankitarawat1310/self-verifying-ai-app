# Manual review: role_scoped_documents


test_create_sets_owner_from_header ............................... OK  
test_owner_can_read_update_and_delete ............................ OK  
test_admin_sees_and_reads_everything ............................. OK  
test_list_shows_only_own_documents ............................... OK  
test_query_parameters_cannot_widen_the_list ...................... OK  
test_reading_another_users_document_is_404 ....................... OK  
test_updating_another_users_document_is_404_and_unchanged ........ OK  
test_deleting_another_users_document_is_404_and_it_survives ...... OK  
test_owner_cannot_be_supplied_or_changed ......................... OK  
test_admin_can_delete_any_document ............................... OK  
test_missing_partial_or_unknown_identity_is_403 .................. Wrong expectation (was test_missing_or_unknown_role_is_rejected; fixed)  
test_blank_title_is_422 .......................................... Not stated (fixed by clarifying the prompt)  
test_unknown_document_is_404_and_a_foreign_one_looks_identical ... OK (added in review)  
test_admin_can_update_any_document_without_taking_ownership ...... OK (added in review)  
test_admin_owner_is_the_caller_and_cannot_be_changed ............. OK (added in review)  
test_patch_updates_only_the_supplied_fields ...................... OK (added in review)  
test_response_fields_match_the_interface ......................... OK (added in review)  
test_query_parameters_cannot_widen_a_single_read ................. OK (added in review)  
test_deleted_document_is_gone_for_everyone ....................... OK (added in review)  
test_missing_required_fields_are_422 ............................. OK (added in review)  

Changes made after review:

- Wrong expectation: the identity check accepted 401 or 403, but the interface declares missing_or_wrong_identity: 403. It now requires exactly 403, adds partial identity (id only, role only) and an unknown role, covers all five routes, and asserts the failed calls changed nothing. Renamed to test_missing_partial_or_unknown_identity_is_403; no security bug referenced the old name.
- Not stated: the blank-title check sent '  ', but only min_length: 1 was declared. Following the other reviewed tasks, the public prompt now says 'Titles cannot be blank.' and both title fields carry description: not blank. The check now covers empty and whitespace-only titles on create and on update, with the document unchanged.
- Added: an unknown document id is 404 for a user and an admin on every route, and another user's document answers identically to a missing one (same status, same body apart from the requested id, nothing leaked).
- Added admin coverage: an admin can update any document without taking ownership; an admin's own document is owned by the admin, an admin cannot supply or change an owner, and users cannot see it.
- Added: partial updates keep the other field; declared response fields on create, read, update and list; query parameters cannot widen a single read or delete; a deleted document is gone for owner and admin; missing title or body is 422.

Remaining lower-priority coverage:

- Unknown query parameters are accepted as either ignored (200/404) or rejected (422); the prompt only requires that they never widen visibility.
- Non-string title or body values, and a PATCH with query parameters, are not tested.
- Whether an admin's PATCH may be an empty object is not stated.

Validation: reference 20/20, stub 0/20, deterministic, 11 automatic bugs caught + security bugs 3/3. The one surviving automatic mutant (min_length=1 removed on the update model) is equivalent: the not-blank validator on the same field also rejects an empty title.


