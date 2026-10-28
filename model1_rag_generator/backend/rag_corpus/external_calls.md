## ext-fixed-endpoint: Fixed outbound endpoint
tags: external-service, security, ssrf
Store the one allowed URL in a module constant and call only that. Never build the URL, host, port or method from
request data; a caller-controlled destination is server-side request forgery (SSRF).

## ext-reject-override: Reject routing fields in requests
tags: external-service, security, validation
Request models for connector routes must forbid extra fields so url, endpoint, target, method, callback or token
fields return 422 before any outbound call is made.

## ext-no-header-forwarding: Do not forward caller headers
tags: external-service, security
Build outbound requests from scratch. Never pass through the incoming Authorization header, cookies or other caller
credentials to a third party.

## ext-timeout: Always set a timeout
tags: external-service, reliability
`httpx.post(URL, json=body, timeout=5.0)`. A call without a timeout can hang the request forever.

## ext-validate-reply: Validate the upstream reply
tags: external-service, validation
Treat the response as untrusted input. Check the status code (`raise_for_status()`), parse JSON, and verify each
field's presence and type (numbers are int or float but not bool; strings are non-blank; enums are in the allowed
set) before using them.

## ext-fail-closed: Fail closed with 502
tags: external-service, reliability, security
If the call errors, times out, returns non-2xx, or returns invalid data, respond 502 and store nothing. Do not
substitute defaults such as price 0 or "unknown" and pretend it worked.
```python
try:
    reply = httpx.post(URL, json=body, timeout=5.0)
    reply.raise_for_status()
    data = reply.json()
except (httpx.HTTPError, ValueError) as error:
    raise HTTPException(502, "upstream failed") from error
```

## ext-send-minimum: Send only what is needed
tags: external-service, privacy
Send the upstream exactly the documented fields, nothing extra. Extra identifiers or internal data in outbound
calls leak information.

## ext-get-params: GET with query parameters
tags: external-service
For GET calls pass inputs with `params={...}` so they are encoded correctly; do not concatenate strings into URLs.

## ext-retries: Bounded retries
tags: external-service, reliability
Retry a fixed number of times, counting the first try as attempt 1. Treat any non-2xx status and any transport error
as a failed attempt. Record the attempt count and the final outcome; after the last failed attempt, mark the item
failed (for example dead-lettered) instead of retrying forever.

## ext-store-after-success: Persist only validated results
tags: external-service, crud
Save the result only after the reply has been validated, so a failed call never leaves a partial record.
