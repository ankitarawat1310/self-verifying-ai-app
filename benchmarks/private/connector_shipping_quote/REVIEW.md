# Manual review: connector_shipping_quote

Reviewer: Ankit  
Date: 2026-09-24

test_quote_returns_201_with_connector_price ........... OK  
test_exactly_one_call_to_the_declared_endpoint ........ OK  
test_quote_is_stored_and_listed ....................... OK  
test_postal_code_length_bounds ........................ OK  
test_small_weight_is_accepted ......................... OK  
test_invalid_input_is_rejected_before_any_call ........ OK  
test_endpoint_override_is_rejected_before_any_call .... OK  
test_malformed_reply_is_502_and_not_stored ............ OK  
test_non_numeric_price_is_502 ......................... OK  
test_connector_error_is_502_and_not_stored ............ OK  
test_missing_fields_are_422 ........................... OK

Changes made after review:

- Confirmed the Day 4 boundary coverage accepts both 0.5 kg and the inclusive 100 kg maximum.
- Extended non-numeric connector-price coverage to reject JSON booleans as well as strings, with no stored result.

Remaining lower-priority coverage:

- Malformed JSON and non-object connector replies.
- Non-finite numeric prices such as NaN or infinity, if the product contract chooses to forbid them explicitly.
- Validation of every declared response field in both create and list responses.

Sign-off: yes for the reviewed rules; remaining items are documented coverage improvements.
