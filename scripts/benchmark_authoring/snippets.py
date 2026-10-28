"""Shared pieces for the new-task authoring scripts."""
from common import STATUS

NO_AUTH = {"scheme": "none"}
HEADERS = {"scheme": "headers", "actor_header": "x-actor-id", "role_header": "x-actor-role"}
STATUS_A = {**STATUS, "missing_or_wrong_identity": 403}
CLOCK = {"header": "x-clock-now", "description": "ISO 8601 timestamp used as the current time when present"}

def caps(*targets):
    out = []
    for t in targets:
        out += [{"kind": "persistence_read", "target": t}, {"kind": "persistence_write", "target": t}]
    return out

NOT_BLANK = '''
def _not_blank(value):
    if isinstance(value, str) and not value.strip():
        raise ValueError("must not be blank")
    return value
'''
IDENTITY = '''
def _identity(actor, role, allowed):
    if not actor or not role or role not in allowed:
        raise HTTPException(403, "caller not allowed")
    return actor, role
'''
CLOCK_FN = '''
def _now(header_value):
    if header_value:
        moment = datetime.fromisoformat(header_value.replace("Z", "+00:00"))
        return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)
'''

