# Manual review: connector_weather_lookup

Reviewer: Ankit  
Date: 2026-09-24

test_lookup_returns_201_with_connector_values .......... OK  
test_exactly_one_get_with_location_query ............... OK  
test_result_is_stored_and_listed ....................... OK  
test_blank_location_is_rejected_before_any_call ........ OK  
test_missing_location_is_rejected_before_any_call ...... OK  
test_endpoint_override_is_rejected_before_any_call ..... OK  
test_unknown_fields_are_rejected ....................... OK  
test_missing_condition_is_502_and_not_stored ........... OK  
test_missing_temperature_is_502_and_not_stored ......... OK  
test_non_numeric_temperature_is_502 .................... OK  
test_blank_condition_is_502 ............................ OK  
test_connector_error_is_502 ............................ OK

Changes made after review:

- Added required-field coverage for an omitted `location`, including no connector call.
- Added 502/no-storage coverage for a connector reply missing `temperature`.
- Extended non-numeric temperature coverage to reject JSON booleans as well as strings.

Remaining lower-priority coverage:

- Malformed JSON and non-object connector replies.
- Non-string `condition` values.
- Validation of every declared response field in both create and list responses.

Sign-off: yes for the reviewed rules; remaining items are documented coverage improvements.
