# Manual review: approval_purchase_request

Reviewer: Ankit  
Date: 2026-09-23

test_submit_returns_201_submitted .............. OK  
test_manager_approves_at_the_5000_limit ........ OK  
test_director_decides_high_value ............... OK  
test_director_can_reject_high_value ............ OK  
test_director_decides_low_value ................ OK  
test_manager_cannot_decide_above_5000 .......... OK  
test_requester_cannot_decide_own_request ....... OK  
test_employee_cannot_decide .................... OK  
test_manager_rejects_at_the_5000_limit ......... OK  
test_terminal_decisions_cannot_change .......... OK  
test_nonpositive_amount_is_422 ................. OK  
test_status_injection_is_422 ................... OK  
test_blank_vendor_is_422 ....................... OK  
test_blank_description_is_422 .................. OK  
test_unknown_request_is_404 .................... OK

Changes made after review:

- The public prompt now explicitly requires nonblank vendor and description values.
- Employee rejection is checked in addition to employee approval.
- Manager rejection at the inclusive 5000 boundary is checked.
- Both terminal states are checked against repeated and opposite decisions.
- Whitespace-only descriptions are checked alongside whitespace-only vendors.

Remaining lower-priority coverage:

- Missing and malformed identity headers.
- Successful and unknown GET behavior, including all declared response fields.
- `decided_by` correctness and preservation after failed decisions.

Sign-off: yes for the reviewed rules; remaining items are documented coverage improvements.
