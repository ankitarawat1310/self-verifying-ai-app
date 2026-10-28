## tst-testclient: Testing with FastAPI TestClient
tags: testing, pytest
```python
from fastapi.testclient import TestClient
from app import app
client = TestClient(app)

def test_new_thing_is_created():
    r = client.post("/things", json={"name": "a"})
    assert r.status_code == 201 and r.json()["id"]
```

## tst-one-rule-per-test: One rule per test
tags: testing, pytest
Write at least one test per stated rule, named after the rule, plus a positive test for the normal path. A failing
test then points straight at the broken rule.

## tst-negative: Test what must be refused
tags: testing, security
For each forbidden action (wrong role, own request, unknown field, invalid value, wrong state) assert the exact
status code and that stored state did not change afterwards.

## tst-boundaries: Boundary tests
tags: testing, validation
Test both sides of every limit: 0 and 0.5 for "positive", 8 and 9 for "at most 8", equal start and end for ordering
rules, exactly the limit for "up to and including".

## tst-unique-data: Independent test data
tags: testing, pytest
Create fresh data in each test with unique values (for example `uuid4().hex[:8]`), so tests do not depend on order or
on each other.

## tst-state-after-error: Check state after a rejected call
tags: testing
After a rejected request, read the record again and compare with before. Many bugs return the right error code but
still apply part of the change.

## tst-hypothesis-basics: Property-based tests with Hypothesis
tags: testing, hypothesis, property-based
State a rule for all inputs and let Hypothesis search for a counterexample:
```python
from hypothesis import given, strategies as st

@given(st.integers(max_value=-1))
def test_negative_amounts_rejected(amount):
    assert client.post("/items", json={"amount": amount}).status_code == 422
```

## tst-hypothesis-stateful: Stateful property tests
tags: testing, hypothesis, state-machine
`hypothesis.stateful.RuleBasedStateMachine` generates random sequences of API calls and checks invariants after
each step, which finds ordering bugs that single-request tests miss.

## tst-mock-upstream: Testing code that calls other services
tags: testing, external-service
Replace the upstream with a fake that records calls and returns chosen replies. Test success, malformed replies and
error statuses, and assert how many calls were made and with what payload.
