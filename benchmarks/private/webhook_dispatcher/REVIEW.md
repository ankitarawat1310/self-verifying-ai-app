# Manual review: webhook_dispatcher



test_delivered_on_first_attempt .......................... OK  
test_delivery_carries_id_type_and_payload ................ OK  
test_retries_until_success ............................... OK  
test_gives_up_after_three_attempts ....................... OK  
test_client_error_status_also_counts_as_failure .......... OK  
test_dead_letters_list_only_failed_events ................ OK  
test_event_can_be_read ................................... OK  
test_unknown_event_type_is_rejected_before_any_call ...... OK  
test_payload_must_be_an_object ........................... OK  
test_caller_cannot_choose_url_status_or_attempts ......... OK  
test_recovers_on_the_second_attempt ...................... OK (added in review)  
test_any_2xx_answer_counts_as_delivered .................. OK (added in review)  
test_every_attempt_resends_the_same_event ................ OK (added in review)  
test_response_fields_match_the_interface ................. OK (added in review)  
test_missing_type_or_payload_is_422_before_any_call ...... OK (added in review)  
test_empty_and_nested_payloads_are_delivered_unchanged ... OK (added in review)  
test_a_3xx_answer_is_not_success ......................... OK (added in review)  

Changes made after review:

- No existing check needed correcting. Verified the queue item: test_retries_until_success uses mock.respond_sequence with (status, body) pairs in the right form. The mock replies 500, 503, 200 in order and then repeats the last reply forever, so what limits the app to three attempts is the exact call-count assertion (3 calls), not the reply order; test_gives_up_after_three_attempts covers the always-failing side.
- Added: a receiver that fails once and then succeeds gives exactly 2 attempts, status delivered, and the event is not dead-lettered.
- Added: 200, 201 and 202 answers are all success (delivered on the first attempt).
- Mutant-driven: the first mutant pass left the 2xx upper bound (300 -> 301) alive, so nothing showed that a 300 answer is a failure. Added test_a_3xx_answer_is_not_success (300 is retried three times, then dead_lettered). This is a realistic mistake, since response.ok-style checks treat anything below 400 as success.
- Added: all three attempts resend the same event id, type and payload.
- Added: declared response fields on the create response, the stored event and the dead-letter entry; the stored event shows dead_lettered with 3 attempts; ids are unique.
- Added: a missing type, a missing payload, and a null or numeric payload are 422 with no delivery.
- Added: an empty object and a nested object (with null, boolean and array values) are delivered exactly as given.

Remaining lower-priority coverage:

- Not testable with the current mock: the prompt also counts 'no answer' (timeout or connection failure) as a failed attempt, but the mock always answers and offers no delay or dropped connection. Only error statuses are covered.
- Only 300 is probed on the 3xx side; other 1xx/3xx codes and redirects with a Location header are not tested.
- Not stated, not tested: the timeout per attempt, any pause between attempts, and behaviour under concurrent events.
- There is no list-all-events route, so a rejected event (422) cannot be shown to leave nothing stored.

Validation: reference 17/17, stub 0/17, deterministic, 11 automatic bugs caught + security bugs 3/3. The one surviving automatic mutant (the initial attempts value 0 -> 1) is equivalent: the retry loop overwrites it before any response is built.


