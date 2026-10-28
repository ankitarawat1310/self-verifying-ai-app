# Manual review: room_booking



test_booking_is_201_and_readable ............................ OK  
test_overlapping_bookings_are_409 ........................... OK  
test_back_to_back_bookings_are_allowed ...................... OK  
test_different_rooms_never_conflict ......................... OK  
test_end_not_after_start_is_422 ............................. OK  
test_four_hour_limit ........................................ OK  
test_unknown_room_is_422 .................................... OK  
test_cancel_frees_the_slot .................................. OK  
test_only_the_booker_can_cancel ............................. OK  
test_list_can_filter_by_room ................................ OK  
test_booked_by_cannot_be_supplied ........................... OK  
test_missing_partial_or_unknown_identity_is_403 ............. Wrong expectation (was test_missing_identity_is_rejected; fixed)  
test_unknown_booking_is_404 ................................. OK  
test_rejected_bookings_do_not_reserve_the_slot .............. OK (added in review)  
test_overlap_is_decided_by_date_and_time_not_time_of_day .... OK (added in review)  
test_response_fields_match_the_interface .................... OK (added in review)  
test_empty_title_missing_fields_and_bad_datetimes_are_422 ... OK (added in review)  

Changes made after review:

- Wrong expectation: the identity check accepted 401 or 403, but the interface declares missing_or_wrong_identity: 403. It now requires exactly 403, adds partial identity (id only, role only) and an unknown role, covers create, list, read and cancel, and asserts the rejected calls created nothing. Renamed to test_missing_partial_or_unknown_identity_is_403; no security bug referenced the old name.
- Verified the Day 4 unknown-booking check (404 on read and cancel) and the unknown-room check against the interface; both stay.
- test_booked_by_cannot_be_supplied is justified by the interface, not the prompt: booked_by is not a declared request field and unknown_body_field is 422.
- Added: bookings rejected with 409 or 422 leave no trace and the slot stays bookable.
- Added: overlap is decided by date and time, not time of day (same clock time on another date is fine; a booking across midnight blocks the next morning).
- Added: declared response fields on create, read and list, and an unfiltered list containing every room.
- Added: empty title, each missing required field and malformed start or end datetimes are 422 and book nothing.

Remaining lower-priority coverage:

- Unclear, not tested: ?room_id= with a room outside room-a/b/c (the interface lists an enum, the prompt does not say whether that is 422 or an empty list).
- Not stated, not tested: whether a cancelled booking stays readable or disappears, and time zone handling for datetimes with offsets.
- Both surviving automatic mutants are equivalent: the DELETE decorator's status_code=204 is overridden by the explicit Response(204), and min_length=1 is backed by the not-blank validator.

Validation: reference 17/17, stub 0/17, deterministic, 10 automatic bugs caught + security bugs 3/3.


