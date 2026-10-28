# Manual review: connector_address_validation

Reviewer: Ankit  
Date: 2026-09-24

test_validation_returns_201_with_connector_values .... OK  
test_exactly_one_post_with_only_the_address .......... OK  
test_result_is_stored_and_listed ..................... OK  
test_invalid_address_result_is_still_stored .......... OK  
test_blank_address_is_rejected_before_any_call ....... OK  
test_endpoint_or_method_override_is_rejected ......... OK  
test_missing_reply_field_is_502 ...................... OK  
test_missing_normalized_address_is_502 ............... OK  
test_non_boolean_valid_flag_is_502 ................... OK  
test_blank_normalized_address_is_502 ................. OK  
test_connector_error_is_502 .......................... OK

Changes made after review:

- Added coverage requiring 502 with no stored result when the connector reply omits `normalized_address`.
- Kept the existing missing-`valid`, invalid-type, blank-value, connector-error, fixed-endpoint, and no-write-on-failure coverage.

Remaining lower-priority coverage:

- Malformed JSON and non-object connector replies.
- Non-string `normalized_address` values.
- Validation of every declared response field in both create and list responses.

Sign-off: yes for the reviewed rules; remaining items are documented coverage improvements.
