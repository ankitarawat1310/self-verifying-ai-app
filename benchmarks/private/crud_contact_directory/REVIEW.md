# Manual review: crud_contact_directory

Reviewer: Ankit  
Date: 2026-09-24

test_create_returns_201_with_id_and_fields .............. OK  
test_created_contact_is_readable_and_listed ............. OK  
test_update_changes_name_and_keeps_id ................... OK  
test_delete_then_read_is_404 ............................ OK  
test_unknown_id_is_404 .................................. OK  
test_duplicate_email_ignoring_case_is_409 ............... OK  
test_update_cannot_take_another_contacts_email .......... OK  
test_invalid_email_is_422 ............................... OK  
test_update_with_invalid_email_is_422 ................... OK  
test_blank_display_name_is_422 .......................... OK  
test_unknown_fields_are_rejected ........................ OK  
test_missing_required_fields_is_422 ..................... OK

Changes made after review:

- Confirmed the Day 4 check rejects malformed email addresses during PATCH and preserves the stored email.
- Extended blank display-name coverage to PATCH for both empty and whitespace-only values.
- Verified that rejected display-name updates leave the stored value unchanged.

Remaining lower-priority coverage:

- A successful email update, including changing only the case of the same contact's address.
- Empty PATCH behavior.
- Validation of every declared response field in create, read, update, and list responses.

Sign-off: yes for the reviewed rules; remaining items are documented coverage improvements.
