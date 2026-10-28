## id-header-identity: Caller identity from headers
tags: identity, headers, access-control
When the contract identifies callers by headers, read both the user id and the role on every protected route and
reject missing or unknown values:
```python
def caller(user: str | None, role: str | None, allowed: set[str]) -> tuple[str, str]:
    if not user or not role or role not in allowed:
        raise HTTPException(403, "not allowed")
    return user, role
```

## id-role-allowlist: Per-route role allowlists
tags: identity, access-control
Give each route its own set of allowed roles taken from the contract. An unknown role is treated like a missing one.
Deny by default: a role not listed for a route cannot use it.

## id-never-trust-body: Identity never comes from the body
tags: identity, security, mass-assignment
Requester, owner, approver and similar fields are taken from the authenticated caller, never from JSON. If the body
contains them, reject with 422 rather than ignoring or trusting them.

## id-bola-404: Object-level authorization
tags: access-control, bola, security
After loading a record, check the caller may see it. For "users only see their own" rules, answer 404 for someone
else's record so its existence is not revealed. Apply the same check to read, update and delete, not only to lists.

## id-admin-override: Admin roles
tags: access-control
When an admin role may see or change everything, branch on role explicitly after identity is established. Keep the
owner check for every other role.

## id-check-order: Order of checks
tags: access-control, errors
A clear order avoids leaking information: identity and role (403), then existence (404), then ownership or
separation of duties (403, or 404 when existence must be hidden), then state (409), then apply the change.

## id-query-no-widen: Query strings do not grant access
tags: access-control, filtering, security
Parameters like `?all=true`, `?owner_id=other` or `?role=admin` must not change what a caller may see. Ignore them or
reject them, but always apply the caller's own visibility rule.

## id-separation-of-duties: Nobody decides their own request
tags: access-control, workflow
Compare the deciding caller's id with the stored requester id and refuse (403) when they match, even if the caller
holds an approving role. Apply it to every decision the rule covers (approve and reject if both are stated).
