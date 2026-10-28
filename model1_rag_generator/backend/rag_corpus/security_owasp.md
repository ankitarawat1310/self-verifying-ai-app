## sec-owasp-api1: OWASP API1 broken object-level authorization
tags: security, owasp, access-control, bola
The most common API flaw: an endpoint takes an object id and returns or changes it without checking the caller
owns it. Check ownership on every object access by id.

## sec-owasp-api3: OWASP API3 property-level authorization
tags: security, owasp, mass-assignment
Covers mass assignment (clients setting fields they should not) and excessive data exposure (responses containing
fields clients should not see). Use explicit request and response shapes.

## sec-owasp-api4: OWASP API4 resource consumption
tags: security, owasp, rate-limit
Bound what one caller can consume: attempt limits, lockouts, maximum sizes, bounded retries.

## sec-owasp-api5: OWASP API5 function-level authorization
tags: security, owasp, access-control
Administrative or approving functions check the caller's role. Hiding a route is not protection.

## sec-owasp-api7: OWASP API7 SSRF
tags: security, owasp, ssrf, external-service
Any feature that fetches a URL can be abused to reach internal systems. Allow only fixed destinations.

## sec-no-secrets-out: Never return secrets
tags: security, passwords
Passwords, password hashes, tokens meant for another channel and internal keys never appear in responses or logs.

## sec-password-hash: Storing passwords
tags: security, passwords
Store a salted slow hash, never the password:
```python
salt = secrets.token_bytes(16)
digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
```
Verify with `hmac.compare_digest` to avoid timing differences.

## sec-no-enumeration: Do not reveal which accounts exist
tags: security, passwords, privacy
Login failures for a wrong password and an unknown user return the same status and message. Password-reset requests
answer identically whether or not the account exists.

## sec-tokens: Secure tokens
tags: security, tokens
Generate tokens with `secrets.token_urlsafe(32)`. Store expiry and a used flag. When a new token is issued for the
same subject, invalidate older ones.

## sec-validation-first: Validate before side effects
tags: security, validation
Validate input fully before touching storage or calling other services. A request rejected with 422 must leave
everything exactly as it was, including one-time tokens.

## sec-least-privilege: Least privilege
tags: security, policy
Import and use only what the task needs: no subprocess, no raw sockets, no filesystem writes, and network calls only
to the declared service. Fewer capabilities means less damage from a bug.
