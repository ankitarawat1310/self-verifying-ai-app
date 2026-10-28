# Manual review: crud_profile_mass_assignment

Reviewer: Ankit  
Date: 2026-09-24

test_create_returns_201_with_only_declared_fields ....... OK  
test_profile_is_readable_and_listed ..................... OK  
test_display_name_can_be_updated ........................ OK  
test_delete_then_404 ..................................... OK  
test_privileged_fields_on_create_are_rejected ........... OK  
test_privileged_patch_is_rejected_without_state_change .. OK  
test_mixed_patch_is_rejected_entirely ................... OK  
test_id_cannot_be_overwritten ........................... OK  
test_duplicate_username_is_409 .......................... OK  
test_blank_values_are_422 ............................... OK

Changes made after review:

- Extended blank username and display-name validation to PATCH and verified the profile remains exactly unchanged.
- Added state-preservation verification after a rejected duplicate-username rename.
- Confirmed privilege fields are rejected individually and when mixed with an allowed update.

Remaining lower-priority coverage:

- Missing required fields during creation.
- Arbitrary non-privilege undeclared fields beyond `id` and the enumerated privilege names.
- Successful username changes and validation of every declared response field.

Sign-off: yes for the reviewed rules; remaining items are documented coverage improvements.
