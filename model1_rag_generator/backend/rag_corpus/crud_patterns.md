## crud-ids: Server-generated ids
tags: crud, security
Generate ids on the server (`uuid4().hex`) and never accept an id from the request body. Return the id in the create
response and store the record under that same id so a follow-up read finds it.

## crud-unique-ci: Case-insensitive uniqueness
tags: crud, uniqueness, validation
When values must be unique "without regard to case", compare normalized forms on every write:
`any(r["key"].lower() == new.lower() for r in STORE.values())`. Return 409 on a clash. Store the original spelling.

## crud-unique-on-update: Uniqueness also applies to updates
tags: crud, uniqueness, update
Re-check uniqueness when an update changes a unique field, excluding the record being updated so renaming to your
own current value is allowed. A create-only check lets an update create a duplicate.

## crud-merge-revalidate: Re-validate after a partial update
tags: crud, update, validation
Rules that span fields must hold after PATCH too. Merge stored values with the changes, validate the merged record,
and only then save. Example: stored start plus a new end must still satisfy the ordering rule; otherwise 422 and
keep the old record.

## crud-atomic-update: Reject the whole update
tags: crud, update
If any field in an update is invalid or forbidden, reject the entire request and change nothing. Do not apply the
valid half of a mixed request.

## crud-delete: Delete semantics
tags: crud, delete
Look the record up first (404 if missing), delete it, return 204. Afterwards reads return 404 and lists no longer
include it.

## crud-list: Listing records
tags: crud, listing
Return a JSON array of records. When the caller can only see some records, filter by the caller's identity on the
server, never by a client-supplied flag.

## crud-server-fields: Server-owned fields
tags: crud, security
Fields such as status, owner, created_by, totals and decision history are set by the server. Leave them off request
models so clients cannot supply them; extra="forbid" then turns attempts into 422.

## crud-immutable: Fields that cannot change
tags: crud, update
Business keys (SKU, codes, usernames when stated) that "cannot be changed" are omitted from the PATCH model. Sending
them is then an unknown field and returns 422, and the stored value stays.

## crud-store-shape: Keep one canonical record
tags: crud
Keep one dict per record with exactly the documented fields and return that dict. Avoid adding extra keys that leak
internal data or privilege information into responses.
