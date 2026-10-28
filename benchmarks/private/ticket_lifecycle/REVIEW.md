# Manual review: ticket_lifecycle


test_open_ticket_is_201_open ................................. OK  
test_agent_starts_and_resolves ............................... OK  
test_requester_closes_resolved_ticket ........................ OK  
test_resolved_ticket_can_be_reopened_by_requester_or_agent ... OK  
test_manager_reopens_closed_ticket ........................... OK  
test_closed_ticket_cannot_be_reopened_without_manager ........ OK  
test_other_customer_cannot_reopen ............................ OK  
test_customer_cannot_resolve_or_start ........................ OK  
test_other_customer_cannot_close ............................. OK  
test_status_order_is_enforced ................................ OK  
test_closing_twice_is_409 .................................... OK  
test_status_injection_is_422 ................................. OK  
test_unknown_ticket_is_404 ................................... OK  
test_missing_partial_or_unknown_identity_is_403 .............. OK (added in review)  
test_only_customers_can_open_tickets ......................... OK (added in review)  
test_only_the_right_role_can_start_resolve_or_close .......... OK (added in review)  
test_actions_that_do_not_fit_the_status_are_409 .............. OK (added in review)  
test_reopened_ticket_can_go_around_the_lifecycle_again ....... OK (added in review)  
test_response_fields_match_the_interface ..................... OK (added in review)  
test_unknown_ticket_is_404_on_every_route .................... OK (added in review)  
test_empty_or_missing_title_and_description_are_422 .......... OK (added in review)  

Changes made after review:

- No existing check needed correcting. Verified the queue item: other-customer reopen coverage exists (test_other_customer_cannot_reopen: 403 and the ticket stays resolved).
- Added the missing-identity coverage the interface requires (missing_or_wrong_identity: 403): no headers, id only, role only and an unknown role are exactly 403 on all six routes and change nothing.
- Added the role matrix: only customers can open tickets; managers cannot start, resolve or close; agents cannot close.
- Added the 409 cases that were missing: reopening an open or in-progress ticket, and starting or resolving a resolved or closed ticket, with the status unchanged.
- Added a full lifecycle after a manager reopen: the ticket is resolved and closed again by its original requester, and another customer still gets 403.
- Added: declared response fields on open, read and every transition, with reads allowed for customer, agent and manager; 404 on every route for an unknown ticket (test_unknown_ticket_is_404 only covered start); empty or missing title and description are 422.

Remaining lower-priority coverage:

- Unclear, not tested: whether a manager may reopen a resolved ticket (the interface says 'requesting customer or agent', the prompt does not exclude managers) or reopen an open or in-progress ticket.
- Not stated, not tested: whether a customer may read another customer's ticket (GET lists the customer role without an ownership rule).
- Not stated: which error wins when both the role and the status are wrong (403 or 409). The checks never combine the two.
- Undeclared fields other than status and requester_id on open rely on the shared unknown_body_field convention only.

Validation: reference 21/21, stub 0/21, deterministic, 11 automatic bugs caught + security bugs 3/3. The one surviving automatic mutant (min_length=1 removed) is equivalent: the not-blank validator on the same fields also rejects empty strings.


