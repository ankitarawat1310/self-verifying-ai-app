# Manual review: approval_emergency_access

Reviewer: Ankit  
Date: 2026-09-23

test_submit_returns_201_submitted .............. OK  
test_duration_boundaries_are_accepted .......... OK  
test_security_officer_can_approve .............. OK  
test_security_officer_can_reject ............... OK  
test_duration_outside_1_to_8_is_422 ............ OK  
test_bypass_fields_are_rejected ................ OK  
test_only_security_officers_decide ............. OK  
test_requester_cannot_self_approve ............. OK  
test_repeated_decisions_are_forbidden .......... OK  
test_blank_justification_is_422 ................ OK  
test_blank_system_name_is_422 .................. OK  
test_missing_identity_is_rejected .............. OK  
test_unknown_request_is_404 .................... OK

Changes made after review:

- The public prompt now explicitly requires nonblank system and justification values.
- The caller-supplied `approver` field is checked alongside `approver_id`.
- Unauthorized-role checks now use actors distinct from the requester, isolating the role rule from self-decision.
- Requester self-rejection is checked in addition to self-approval.
- Both approved and rejected terminal states are checked against repeated and opposite decisions.
- Whitespace-only system names are checked alongside justifications.
- Identity failures now require the interface-declared 403 and cover missing, partial and invalid identity.

Remaining lower-priority coverage:

- Successful and unknown GET behavior, including all declared response fields.
- Correct `decided_by` recording and preservation after failed decisions.
- State preservation after all rejected identity and injection attempts.

Sign-off: yes for the reviewed rules; remaining items are documented coverage improvements.
