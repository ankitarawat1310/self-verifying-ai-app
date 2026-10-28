# Manual review: approval_leave_request

Reviewer: Ankit  
Date: 2026-09-24

test_submit_returns_201_submitted_with_requester_from_header .. OK  
test_request_can_be_read ....................................... OK  
test_manager_can_approve ....................................... OK  
test_manager_can_reject ........................................ OK  
test_same_day_leave_is_allowed ................................. OK  
test_requester_cannot_self_approve_even_as_manager ............. OK  
test_employee_role_cannot_decide ............................... OK  
test_only_employees_submit ..................................... OK  
test_end_before_start_is_422 ................................... OK  
test_caller_cannot_set_status_or_requester ..................... OK  
test_terminal_decisions_cannot_change .......................... OK  
test_unknown_request_is_404 .................................... OK  
test_blank_reason_is_422 ....................................... OK

Changes made after review:

- Missing identity on submission now requires the interface-declared 403 instead of accepting either 401 or 403.

Remaining lower-priority coverage:

- Missing, partial, and invalid identity headers on read and decision routes.
- Explicit self-rejection coverage; approval and rejection currently share the same decision guard.
- Unknown GET behavior and validation of every declared response field, including `decided_by`.
- State preservation after each failed decision attempt.

Sign-off: yes for the reviewed rules; remaining items are documented coverage improvements.
