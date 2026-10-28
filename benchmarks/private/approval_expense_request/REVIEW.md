# Manual review: approval_expense_request

Reviewer: Ankit  
Date: 2026-09-23

test_submit_returns_201_submitted .................. OK  
test_request_can_be_read ........................... OK  
test_manager_can_approve ........................... OK  
test_manager_can_reject ............................ OK  
test_employee_cannot_approve_or_reject ............. OK  
test_requester_cannot_self_approve_even_as_manager . OK  
test_terminal_decisions_cannot_change .............. OK  
test_approval_is_not_repeatable .................... OK  
test_status_and_requester_injection_is_422 ......... OK  
test_nonpositive_or_non_numeric_amount_is_422 ...... OK  
test_blank_description_is_422 ...................... OK  
test_missing_identity_is_rejected .................. OK  
test_unknown_request_is_404 ........................ OK

Changes made after review:

- The public prompt now explicitly requires a nonblank description.
- The prompt now aligns with the private state machine by forbidding both self-approval and self-rejection.
- Self-rejection is tested in addition to self-approval.
- Both terminal states are tested against repeated and opposite decisions with state preservation.
- Whitespace-only descriptions are rejected explicitly.
- Identity failures now require the interface-declared 403 and cover missing, partial and invalid identity.

Remaining lower-priority coverage:

- Unknown GET behavior and validation of every declared response field.
- Submission attempts by a manager and read attempts using invalid roles.
- `decided_by` preservation after every failed terminal transition.

Sign-off: yes for the reviewed rules; remaining items are documented coverage improvements.


Addition after review (2026-09-24, Claude, from the Day 3 bug-generator gap list):

- `test_small_positive_amount_is_accepted`: a 0.5 amount must be accepted. The prompt says "a positive amount", and without this check a bug requiring amount > 1 went unnoticed. Needs reviewer sign-off.
