## wf-state-machine: Model workflows as explicit transitions
tags: workflow, state-machine
Write the allowed moves as data and check them on every action:
```python
MOVES = {("draft", "submit"): "submitted", ("submitted", "close"): "closed"}
def move(record, action):
    key = (record["state"], action)
    if key not in MOVES:
        raise HTTPException(409, "not allowed in this state")
    record["state"] = MOVES[key]
```

## wf-terminal: Terminal states stay terminal
tags: workflow, state-machine
Final states (approved, rejected, paid, closed unless reopening is stated) accept no further transitions. Repeating
or reversing a decision returns 409 and leaves the stored state unchanged.

## wf-initial-state: Initial state is set by the server
tags: workflow, state-machine, security
New records always start in the documented initial state. A client that sends a status on create gets 422.

## wf-role-per-transition: Roles per transition
tags: workflow, access-control
Each transition names who may perform it. Check the role for that specific action (403 if not allowed) before
checking whether the state allows it (409).

## wf-decision-record: Record who decided
tags: workflow, audit
Store the deciding caller's id and return it, so decisions are attributable. Never accept it from the body.

## wf-thresholds: Approval limits
tags: workflow, access-control, numbers
Limits like "managers up to and including 5000" are inclusive (`amount <= 5000` allowed). Apply the limit to every
decision it covers, approve and reject alike, unless the requirement limits it to one.

## wf-reopen-rules: Reopening
tags: workflow, state-machine
When reopening is allowed only from certain states or by certain roles, encode both. A rule like "closed items can
be reopened only by a manager" means other roles get 403 on closed items even if they may reopen from other states.

## wf-single-use: One-time actions
tags: workflow, security
Things that work once (tokens, invitations, payments) are marked used in the same step that consumes them, and every
later attempt fails.

## wf-graph-deps: Dependencies between items
tags: workflow, graph
Check that referenced items exist (422 otherwise), refuse self-references, and before adding an edge A depends on B,
refuse it if B already depends on A directly or transitively (a cycle, 409). Search with a stack or recursion over
the dependency lists.

## wf-complete-after-deps: Completion order
tags: workflow, graph
An item completes only when all of its dependencies are complete; otherwise 409. Once complete, do not accept new
unfinished dependencies for it (409), or the invariant breaks.
