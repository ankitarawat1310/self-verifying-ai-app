# Manual review: connector_document_delivery

Reviewer: Ankit  
Date: 2026-09-24

test_delivery_returns_201_with_connector_values ........ OK  
test_exactly_one_post_with_only_declared_fields ......... OK  
test_delivery_is_stored_and_listed ...................... OK  
test_injected_fields_are_rejected_before_any_call ....... OK  
test_caller_authorization_header_is_not_forwarded ....... OK  
test_unexpected_status_is_502_and_not_stored ............ OK  
test_missing_delivery_id_is_502 ......................... OK  
test_blank_delivery_id_is_502 ........................... OK  
test_missing_status_is_502 .............................. OK  
test_connector_error_is_502 ............................. OK  
test_blank_fields_are_rejected_before_any_call .......... OK  
test_missing_fields_are_422 ............................. OK

Changes made after review:

- Added coverage for blank connector-supplied `delivery_id` values.
- Added coverage for connector replies missing `status`.
- Corrected the missing-fields check so it exercises both missing `document_id` and missing `recipient`.

Remaining lower-priority coverage:

- Malformed JSON and non-object connector replies.
- Non-string `delivery_id` values.
- Validation of every declared response field in both create and list responses.

Sign-off: yes for the reviewed rules; remaining items are documented coverage improvements.
