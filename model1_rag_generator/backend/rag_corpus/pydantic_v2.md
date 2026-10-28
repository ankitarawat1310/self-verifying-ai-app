## pd-forbid-extra: Reject unknown fields (mass assignment)
tags: pydantic, validation, security, mass-assignment
Set `model_config = ConfigDict(extra="forbid")` on every request model. Unknown fields such as role, is_admin,
status or id then fail with 422 instead of being silently ignored or, worse, stored. Silently ignoring extra fields
hides client mistakes and attacks alike.

## pd-field-constraints: Numeric and length constraints
tags: pydantic, validation
Use `Field` bounds: `amount: float = Field(gt=0)` for strictly positive, `ge=0` for nonnegative, `le=` for upper
bounds, `min_length=`/`max_length=` for strings. Read the requirement carefully: "at most 8" is `le=8`, "more than 0"
is `gt=0`, "up to and including" is inclusive.

## pd-strict-int: Whole numbers only
tags: pydantic, validation
`int` in lax mode accepts 2.0 and "2". When a count must be a whole number, use `StrictInt` so 1.5 and "3" are
rejected with 422. Combine with Field bounds: `hours: StrictInt = Field(ge=1, le=8)`.

## pd-not-blank: Rejecting blank strings
tags: pydantic, validation
`min_length=1` still accepts "   ". Add a validator:
```python
@field_validator("title")
@classmethod
def not_blank(cls, value: str) -> str:
    cleaned = value.strip()
    if cleaned == "":
        raise ValueError("value is blank")
    return value
```

## pd-email: Validating email addresses
tags: pydantic, validation
Use `EmailStr` (needs the email-validator package). Compare emails case-insensitively when uniqueness is required,
because users type the same address with different capitalization.

## pd-cross-field: Rules that involve two fields
tags: pydantic, validation, time
Use a model validator for rules like end after start:
```python
@model_validator(mode="after")
def check_order(self):
    if self.finish <= self.begin:
        raise ValueError("finish must be after begin")
    return self
```
Decide whether equality is allowed from the wording: "after" excludes equal, "cannot precede" allows it.

## pd-partial-update: PATCH models
tags: pydantic, crud, update
Make every field optional with a default of None and apply only what the client sent:
`changes = payload.model_dump(exclude_unset=True)`. Fields that must never change after creation (keys, owners,
codes) are simply not declared on the PATCH model, so extra="forbid" rejects them.

## pd-literal: Closed sets of values
tags: pydantic, validation
Use `Literal["a", "b"]` for fields limited to fixed values so anything else returns 422 automatically.

## pd-dates: Dates and datetimes
tags: pydantic, time, validation
Annotate with `date` or `datetime`; Pydantic parses ISO strings and returns 422 for "tomorrow". Serialize with
`model_dump(mode="json")` or `.isoformat()`.

## pd-v2-syntax: Pydantic v2, not v1
tags: pydantic, pitfalls
Use `model_dump()` not `.dict()`, `model_validate()` not `.parse_obj()`, `Field(pattern=...)` not `regex=`,
`@field_validator` with `@classmethod` not `@validator`, `ConfigDict` not `class Config`. v1 syntax fails at import.

## pd-optional-defaults: Optional fields need defaults
tags: pydantic, pitfalls
`note: str | None` without a default is still required. Write `note: str | None = None`.

## pd-object-field: Arbitrary JSON objects
tags: pydantic, validation
A field that must be a JSON object is `dict[str, Any]`; strings and lists then fail with 422. A list of nested
models is `list[LineModel] = Field(min_length=1)` when at least one entry is required.
