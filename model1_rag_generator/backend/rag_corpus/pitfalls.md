## pit-201-vs-200: Wrong success codes
tags: pitfalls, status-codes
A create that returns 200 instead of 201, or a delete that returns 200 with a body instead of 204, fails contract
checks even when the logic is right.

## pit-ignored-extra: Silently ignoring fields
tags: pitfalls, pydantic, security
Pydantic's default ignores unknown fields. That hides privilege-escalation attempts and typos. Forbid them.

## pit-broad-except: Catching too much
tags: pitfalls, errors
`except Exception: pass` turns real failures into silent success. Catch the specific errors you expect and convert
them to the documented status code.

## pit-validation-after-write: Validating after saving
tags: pitfalls, validation
Saving first and validating later leaves bad data behind when validation fails. Validate, then save.

## pit-float-equality: Float equality
tags: pitfalls, money, numbers
`0.1 + 0.2 == 0.3` is False. Use Decimal for money and compare rounded values.

## pit-naive-datetime: Mixing naive and aware datetimes
tags: pitfalls, time
Comparing a naive datetime with an aware one raises TypeError. Normalize all datetimes to aware UTC at the boundary.

## pit-list-only-auth: Authorizing lists but not items
tags: pitfalls, access-control, bola
Filtering the list endpoint by owner is not enough; read, update and delete by id need the same check.

## pit-mutable-default: Mutable default arguments
tags: pitfalls, python
`def f(items=[])` shares one list across calls. Use `None` and create the list inside the function, or
`Field(default_factory=list)` in models.
