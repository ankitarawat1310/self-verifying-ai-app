# Manual review: crud_appointment_registry

Reviewer: Ankit  
Date: 2026-09-24

test_create_returns_201 ................................. OK  
test_appointment_is_readable_and_listed ................. OK  
test_valid_patch_moves_the_window ....................... OK  
test_delete_then_404 ..................................... OK  
test_end_before_start_is_422 ............................. OK  
test_end_equal_to_start_is_422 ........................... OK  
test_invalid_datetime_is_422 ............................. OK  
test_duplicate_code_is_409 ............................... OK  
test_partial_update_cannot_break_the_time_rule ........... OK  
test_blank_title_is_422 .................................. OK  
test_unknown_fields_are_rejected ......................... OK

Changes made after review:

- Confirmed the Day 4 equality case rejects an end-only PATCH that makes end equal to the stored start.
- Extended partial-update coverage to reject start-only PATCH operations that make start equal to or later than the stored end.
- Verified that both stored timestamps remain unchanged after all rejected partial updates.

Remaining lower-priority coverage:

- Successful title-only and start-only PATCH operations.
- Missing required create fields and blank appointment codes.
- Validation of every declared response field and unknown PATCH/GET routes separately.

Sign-off: yes for the reviewed rules; remaining items are documented coverage improvements.
