# M2: spec-first synthesis

M2 writes and checks a behavior spec before any code exists, then builds both the app and its tests from that frozen spec.

## Steps

1. **Author the spec (LLM).** The model gets the requirement and a skeleton built from the public interface (every route with its roles). It fills in what the interface doesn't say:
   - which route creates, reads or acts on which entity;
   - the status state machine (initial, states, terminal) and each action's moves, with per-move roles;
   - rules: `not_self` (requester can't approve own request), `owner_only`, `field_order` (start <= end), `unique`, `custom`;
   - invariants and an import/host policy.

   The reply is forced into the `BehaviorSpec` JSON schema (Ollama structured output).
2. **Pin to the interface.** Routes and roles always come from the interface. The run record notes any route the model added, dropped or re-roled.
3. **Check the spec.**
   - Structural checks against the interface: known routes, roles, states and fields.
   - A bounded model checker (depth 6) over each state machine. It explores every operation sequence from the initial state, with abstract actors (the owner and a non-owner). It checks five things:
     - every state is reachable;
     - terminal states have no way out;
     - no non-terminal dead ends;
     - each action is deterministic;
     - each move can be made by someone under the spec's own rules.
   - Any failures go back to the model once. If the spec still fails, M2 falls back to the interface-only skeleton and records `spec_source = skeleton_fallback`.
4. **Freeze.** The spec's SHA-256 is recorded and written to `behavior_spec.sha256` before code generation. The gate rejects the run if the spec changes afterwards.
5. **Synthesize the app (LLM).** The model writes `app_code` only, from the frozen spec. It uses the same generator rules as M0/M1 and the same hybrid retrieval as M1 (`SVAGA_M2_RETRIEVAL=0` turns retrieval off for an ablation).
6. **Generate tests from the spec (code, no LLM).** `spec_first/spec_tests.py` writes one parametrized test file covering:
   - route exists; create happy path; unknown field / missing field / blank / out-of-range / bad enum -> 422;
   - no identity / wrong role -> 403; unknown id -> 404;
   - initial state; every transition; `not_self` / `owner_only` violations; every action from a state it doesn't allow -> 409;
   - `field_order` and `unique` rules.

   It skips (and records) cases it can't build honestly. Examples: a required array described only in words, or tasks that call an outside service (the sandbox has no mock).
7. **Verify and gate.** Same verifiers and release gate as M1.

## Checks on the generator (Day 7)

- Skeleton specs for all 20 tasks: the generated tests pass 100% on every reference app (no false alarms).
- Hand-written specs for `approval_leave_request` (24 cases) and `ticket_lifecycle` (35 cases) also pass 100% on the references.
- Seeded bugs caught by spec tests alone:

  | Task | Spec | Caught |
  |---|---|---|
  | leave | hand spec | 13/14 |
  | ticket | hand spec | 9/14 |
  | expense | skeleton | 10/15 |
  | contact | skeleton | 7/14 |
  | room | skeleton | 4/13 |

  A richer spec catches more, and that is what the LLM's spec adds.

## Files

- `svaga_platform/app/spec_first/`:
  - `behavior_spec.py`: the model and the skeleton;
  - `spec_check.py`: the validator and model checker;
  - `spec_tests.py`: the test generator;
  - `author.py`: the LLM steps.
- `svaga_platform/app/pipelines/m2_spec_first.py`: the pipeline.
- `tests/test_m2_spec_first.py`; the fixtures are in `tests/fixtures/m2_specs/`.
- `scripts/m2_probe.py`: real-model probe on the dev tasks (spec quality, reference pass rate, bugs caught, optional full run).

## Known limits

- One state machine per entity, and one owner field per rule.
- Rules the model marks `custom` are passed to the synthesizer but get no generated test.
- Connector tasks get validation and auth tests only; their happy paths are left to the hidden judge.

## First qwen probe (Sep 25, `results/m2_probe/20260925_074813`) and the fixes it led to

| Task | Spec source | Tests passing on reference | Planted bugs caught (reported) |
|---|---|---|---|
| expense | fallback | 15/15 | 10/15 |
| contact | qwen | 7/13 | 14/14 |
| profile | qwen | 12/15 | 12/12 |
| room | qwen | 16/16 | 4/13 |
| webhook | fallback | 7/7 | 5/14 |

- **Expense:** qwen used `field_order` for single-field limits ("amount > 0"). The validator rejected the spec twice, so M2 fell back.
- **Contact and profile:** qwen wrote nonsense rules (`display_name >= email`, owner rules on an API with no identity headers, 422 instead of 409/403). They produced tests that fail on the correct app. That also made "bugs caught" look better than it was, because a test that fails on everything "catches" everything.
- **Webhook:** qwen correctly saw that the create call ends in `delivered` or `dead_lettered`, but the spec language had no way to say "decided during create", so M2 fell back.

Fixes:
- Rule checks are now type-aware: `field_order` only compares two dates, datetimes or numbers; owner rules need identity headers and an actor-id field. Rules that can't apply are dropped, and each drop is recorded.
- Rule status codes are set from the interface's meanings (forbidden, conflict, validation_error).
- The create operation may list several outcome states.
- Owner rules on non-state routes (e.g. "only the booker can cancel") now get tests.
- The probe counts a bug as caught only when a test that passes on the reference fails on the buggy app. It also lists false alarms.

Replaying qwen's own specs after the fixes:

| Task | Tests passing on reference | Planted bugs caught |
|---|---|---|
| contact | 11/11 | 8/14 |
| profile | 13/13 | 8/12 |
| room | 17/17 | 5/13 |

## Second qwen probe (`results/m2_probe/20260925_080741`) and fixes

- **Expense: the fix round worked.** qwen's first spec made approve/reject impossible (owner_only and not_self together). The model checker said so, and qwen's second spec was correct: draft -> submitted on create, then manager approve/reject with not_self. Three tests still failed on the reference, because they expected the status right after create to be "draft". **Fix:** the state a client sees after create is the create step's outcome when there is exactly one; "draft" is never tested. Replayed: 24/24 on the reference and 14/15 planted bugs caught (the skeleton caught 10/15). This spec is now the test fixture `approval_expense_request.qwen.json`.
- **Room: qwen wrote `start_at > end_at` as the required rule.** The tests built from it sent invalid bookings, so create failed and 5 tests failed on the reference. **Fix:** a start/end lint that sends this back to the model.
- **Webhook: qwen again used unreachable states.** It didn't use create outcomes. **Fix:** the checker's message now tells the model to put create-time outcomes on the create operation.
- **Also fixed:** owner rules on a create route are dropped (no owner exists yet).

## Third qwen probe (`results/m2_probe/20260925_083807`): clean

| Task | qwen spec: attempts | Tests passing on reference | Bugs caught, qwen spec | Bugs caught, interface-only spec |
|---|---|---|---|---|
| expense | 2 (checker fixed an impossible approve rule) | 24/24 | 14/15 | 10/15 |
| contact | 1 | 11/11 | 8/14 | 7/14 |
| profile | 1 | 13/13 | 8/12 | 7/12 |
| room | 2 (lint fixed reversed start/end) | 17/17 | 5/13 | 4/13 |
| webhook | 1 (used create outcomes) | 7/7 | 5/14 | 5/14 |
| **Total** | | **72/72, no false alarms** | **40/68 (59%)** | **33/68 (49%)** |

- Spec authoring takes 7 to 22 seconds per task on qwen3-coder:30b.
- The spec check changed the outcome twice: once from the model checker, once from the lint.

## First full M2 smoke run (`results/m2_probe/20260926_095922`, qwen3-coder:30b)

| Task | M2 decision | Hidden judge | Why |
|---|---|---|---|
| expense | REJECT | 3/14 | App typed `x-actor-id` as a UUID, so every call with an ordinary actor id got 422. Spec tests caught it. |
| contact | REJECT | 11/12 | Accepted unknown body fields. Spec test `extra_field` failed, and so did the matching hidden check. |
| profile | **ACCEPT** | 9/10 | **False assurance.** GET /profiles returned `{"profiles": [...]}` instead of a bare array. Nothing in M2 checked this. |
| room | REJECT | 1/17 | Crash: `datetime.timedelta` on the class. Spec tests caught it. |
| webhook | REJECT | 14/17 | Accepted a caller-supplied `url` (spec test `extra_field`), and no retries (the sandbox can't test those). |

- Every rejection was a real bug.
- The one acceptance was wrong because the interface never said list routes return a bare array. The hidden checks assume they do, and all 11 reference list routes return one.

Fixes (before the freeze; they apply to every model):
- **Interface text for list routes** now says "a JSON array (a bare list, not wrapped in an object)".
- **Generator rules, shared by M0, M1 and M2:**
  - identity headers are plain strings, `Optional[str] = Header(None)`, with missing or unknown identity -> 403 (not 422);
  - list routes return bare arrays;
  - self-tests compare normalized values case-insensitively.
- **New spec-test case `list_shape`:** the route returns a JSON array. When there are no identity headers, the created record must also appear in it.
- **Skeleton spec tests are now checked against all 20 references** in the test suite (they had covered the 5 dev tasks). That caught one false alarm in the new case (role-scoped lists), which is fixed.
- **The probe now saves each run's verification report and judge result**, and prints which verifiers failed.

## Second full smoke run (`results/m2_probe/20260926_101100`)

- M2 rejected all 5 apps, and each rejection was right: none of the apps passed every hidden check. **No false assurance.**
- The profile app's list route is now a bare list, so the list-shape fix worked.
- What broke this time (ordinary code bugs, the kind M4's repair loop exists for):

| Task | Hidden checks | Bug in qwen's app |
|---|---|---|
| expense | 3/14 | `actor_id: Optional[str] = Header(None)` reads a header named "actor-id", not "x-actor-id", so every call looked anonymous (403). |
| profile | 1/10 | The response model was built with `None` for username and display_name, so create crashed (500). |
| room | 2/17 | `timedelta` used without being imported (500). |
| contact | 11/12 | Still accepts unknown body fields. |
| webhook | 13/17 | Makes 3 attempts even when the first succeeds; accepts a caller-supplied `url`. |

- **Fix:** the generator rule now names the header exactly: `Header(None, alias="x-actor-id")`.
- The other failures are app-code bugs, not problems with the spec or the prompt. From here on they belong to M4 (repair), not more prompt tuning.
