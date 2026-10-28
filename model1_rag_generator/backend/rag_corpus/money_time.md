## mt-decimal-money: Money with Decimal
tags: money, numbers
Floats cannot represent 0.1 exactly, so 0.1 + 0.2 becomes 0.30000000000000004. Sum money with `Decimal(str(x))`
and round once at the end: `total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`. Return `float(total)` only
after rounding.

## mt-compare-money: Comparing amounts
tags: money, numbers
Compare amounts after quantizing both sides to cents, not with float equality. "Exactly the total" means equal to
the cent.

## mt-server-totals: Totals are computed, not accepted
tags: money, security
Never accept totals, subtotals or discounts from the client. Compute them from stored line items on every change and
reject client-supplied values with 422.

## mt-positive: Positive and nonnegative amounts
tags: money, validation
"Positive" means greater than zero (`gt=0`); zero is invalid, 0.5 is valid. "Nonnegative" allows zero (`ge=0`).
Test both sides of every boundary.

## mt-aware-now: Current time
tags: time
Use timezone-aware UTC: `datetime.now(timezone.utc)`. Parse incoming timestamps with `datetime.fromisoformat`, treat
a trailing Z as +00:00, and attach UTC to naive values before comparing.

## mt-test-clock: Injectable clock
tags: time, testing
When a contract offers a test clock header, read "now" from it when present and fall back to the system clock. Pass
that single value through the request instead of calling now() in several places.

## mt-expiry: Expiry checks
tags: time, security
Store the expiry instant when something is issued (`issued + timedelta(minutes=60)`) and reject when
`now >= expires`. Check expiry at the moment of use, not only when listing.

## mt-lockout-window: Lockouts
tags: time, security, rate-limit
Count consecutive failures per account, lock when the count reaches the limit, store the unlock time, and refuse all
attempts (even correct ones) until then. Reset the counter on success and when a lock is applied.

## mt-overlap: Interval overlap
tags: time, scheduling
Two half-open intervals [s1, e1) and [s2, e2) overlap exactly when `s1 < e2 and s2 < e1`. This catches partial
overlap, containment and identical intervals, and allows back-to-back bookings where one ends as the next starts.
Checking only whether the new start falls inside an existing interval misses cases.

## mt-duration-limit: Duration limits
tags: time, scheduling, validation
Compute `end - start` as a timedelta and compare with the limit: "at most 4 hours" allows exactly 4 hours.
