# Manual review: crud_inventory_tracker

Reviewer: Ankit  
Date: 2026-09-24

test_create_returns_201_with_fields ......................... OK  
test_item_is_readable_and_listed ............................ OK  
test_patch_updates_stock .................................... OK  
test_delete_then_404 ........................................ OK  
test_negative_stock_is_422 ................................. OK  
test_fractional_stock_is_422 ............................... OK  
test_blank_name_is_422 ...................................... OK  
test_duplicate_sku_ignoring_case_is_409 .................... OK  
test_patch_to_negative_stock_is_rejected_and_unchanged ..... OK  
test_sku_cannot_be_changed .................................. OK  
test_unknown_fields_are_rejected ............................ OK

Changes made after review:

- Extended integer-only stock validation to PATCH and verified rejected fractional updates preserve stored stock.
- Extended empty and whitespace-only name validation to PATCH and verified rejected updates preserve the stored name.
- Added PATCH coverage for a general undeclared field in addition to the protected SKU field.

Remaining lower-priority coverage:

- Missing required fields during creation and boolean stock values.
- Successful name-only PATCH and setting stock to the zero boundary via PATCH.
- Validation of every declared response field and unknown DELETE behavior.

Sign-off: yes for the reviewed rules; remaining items are documented coverage improvements.
