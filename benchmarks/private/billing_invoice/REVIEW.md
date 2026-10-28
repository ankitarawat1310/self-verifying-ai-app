# Manual review: billing_invoice

Reviewer: Ankit  
Date: 2026-09-24

test_create_computes_total_and_starts_draft ............. OK  
test_total_is_rounded_to_cents .......................... OK  
test_adding_a_line_updates_the_total .................... OK  
test_issue_then_pay_exact_total ......................... OK  
test_client_cannot_set_total_or_status .................. OK  
test_line_item_cannot_carry_its_own_total ............... OK  
test_empty_invoice_is_422 ............................... OK  
test_empty_customer_or_description_is_422 .............. OK  
test_invalid_quantity_or_price_is_422 ................... OK  
test_no_line_items_after_issue .......................... OK  
test_wrong_payment_amount_is_422_and_unpaid ............. OK  
test_state_order_is_enforced ............................ OK  
test_unknown_invoice_is_404 ............................. OK

Changes made after review:

- Confirmed the expanded Day 4 cent-rounding cases, including 0.10 + 0.20 and 3 x 1.10.
- Extended line-item extra-field validation to the add-line route and verified the total remains unchanged.
- Extended quantity and price validation to the add-line route and verified rejected lines do not change the total.
- Added declared minimum-length coverage for empty customers and line-item descriptions.

Remaining lower-priority coverage:

- Missing and unknown invoice behavior on the add-line and pay routes.
- Unknown payment fields and non-numeric payment amounts.
- Validation of every declared response field after each state transition.

Sign-off: yes for the reviewed rules; remaining items are documented coverage improvements.
