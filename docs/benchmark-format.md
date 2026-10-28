# Benchmark v1 task format

Each task is split into a public half (what every model sees) and a private half (what only the judge sees).
The split is what makes "false assurance" measurable: a model cannot be graded on answers it was shown.

```
benchmarks/
  schema/task_public.schema.json     rules for public task files
  schema/task_private.schema.json    rules for private task files
  public/<task_id>/task.yaml         prompt + interface (routes, roles, status-code conventions, optional test clock)
  private/<task_id>/private.yaml     canary, split, gold capabilities, state machine, hidden check list, security mutants
  private/<task_id>/checks/test_hidden.py   black-box HTTP checks
  private/<task_id>/reference/app.py        known-correct app (standalone FastAPI, in-memory)
  private/<task_id>/mutants/                seeded bugs: auto_*.py, sec_*.py, manifests, security.yaml
  workflows/*.yaml                   legacy v0 tasks, kept so old runs and tests still work
```

## Public half (`task.yaml`)

| Field | Meaning |
| --- | --- |
| `task_id`, `title` | Folder name and display name |
| `category` | One of `data_rules`, `access_control`, `workflow_state`, `scheduling`, `external_service` |
| `source` | `svaga2`, `svaga3`, `baxbench` or `new` |
| `prompt` | The plain-English request |
| `interface.auth` | How the caller is identified (for example headers `x-actor-id` and `x-actor-role`) |
| `interface.status_codes` | Shared conventions, for example validation error 422, forbidden 403 |
| `interface.clock` | Optional header carrying "now", so time rules (expiry) can be tested without waiting |
| `interface.roles`, `interface.routes` | Exact routes, request fields, success status and response fields |
| `interface.mock_services` | For connector tasks: the only outbound call the app may make |

The interface is rendered as text and appended to the prompt, so every model gets the same contract
(`shared/benchmarks/task_package.py`, `render_interface_text`).

## Private half (`private.yaml`)

| Field | Meaning |
| --- | --- |
| `canary` | Unique marker. Tests fail if it ever appears in a prompt or a generated file |
| `split` | `unassigned`, `dev` (tuning allowed) or `test` (frozen, reported numbers only) |
| `gold_capabilities` | Minimum permissions the app needs; used for permission excess |
| `state_machine` | Allowed states and moves, with the roles allowed to make each move |
| `hidden_checks` | IDs and descriptions of the tests in `checks/test_hidden.py`, tagged functional or safety |
| `security_mutants` | Unused; hand-written security bugs live in `mutants/security.yaml` (see below) |

## Rules enforced by tests (`tests/test_task_package.py`)

1. Every public task has matching private data, and every canary is unique.
2. The adapter that feeds pipelines carries no private data: empty `permission_requirements`, no properties,
   no hidden check names, no canary.
3. No model-facing module (pipelines, generator, LLM providers, spec author, verifiers) imports
   `shared.benchmarks.private_loader` or names the private folder.
4. Canary test: M1 to M4 run on a v1 task with a recording LLM; the canary never appears in any prompt,
   generated file or run metadata. Verified to fail when a canary is planted in a prompt.

## Why the legacy format was not reused

The v0 YAML put `permission_requirements` (the expected policy) in the same file the pipelines read, and
`default_policy_from_benchmark` copied it into the generated app's policy. That handed every model the answer
to the permission-excess metric. v1 moves gold capabilities to the private half.

## Hidden checks and the judge

The judge (`svaga_platform/app/judge/`) starts the candidate `app.py` with uvicorn in a separate process, in a fresh
temporary folder, with a minimal environment (no API keys), then runs the task's hidden checks against it over HTTP.

Rules for writing a hidden check (`checks/test_hidden.py`):

- One `test_*` function per check. Its docstring starts with `[functional]` or `[safety]`; `private.yaml`'s
  `hidden_checks` list is generated from these docstrings, so the two cannot drift apart.
- Black-box only: use the `client` fixture (an `httpx.Client` pointed at the running app). Never import the app.
- Each check creates its own data through the API and uses `uid()` for unique names, so checks do not depend on
  each other or on seed files. The app is started once per judge run.
- A check that expects 404 or 403 first proves the route exists (for example by a successful create), otherwise an
  empty app would pass it.
- Header identity: `actor(user_id, role)` returns `x-actor-id` / `x-actor-role` headers.
- Connector tasks: the `mock` fixture is a real HTTP service on `127.0.0.1:18765`. Program replies with
  `mock.respond(method, path, status=..., json_body=...)` and inspect `mock.calls` (method, path, query, json, headers).
- Only test what the prompt or the public interface states.

`scripts/validate_benchmark.py [task_ids] [--repeat N] [--json out.json]` checks every task: reference passes 100%,
empty stub passes 0%, identical results across repeats, at least 10 checks. `tests/test_judge.py` runs the same
guarantees in the normal test suite.

## Seeded bugs

Two kinds of deliberately broken copies of each reference app live in `mutants/`:

| Kind | Made by | Kept when |
| --- | --- | --- |
| `auto_*.py` | `scripts/generate_mutants.py`: one-line changes with 6 operators (flip a comparison, disable a guard, change a status code, swap and/or or True/False, loosen validation, off by one), 12 sampled per task with seed 7 | at least one hidden check fails (bugs that change nothing observable are recorded as survived, not kept) |
| `sec_*.py` | `scripts/build_security_mutants.py` from `mutants/security.yaml` (written by `scripts/benchmark_authoring/security_mutants.py`): 3 hand-written security bugs per task | caught AND caught by the check it targets |

These are the faults behind the property-violation-recall metric: how many of them a model's own tests and
verifiers reject. Rerun both scripts for a task whenever its hidden checks change.

## Split and freeze

`scripts/freeze_benchmark.py` keeps the numbers honest:

| Command | What it does |
| --- | --- |
| `split` | Draws the dev/test split with seed 2026: one dev task per category (5 dev, 15 test), saved to `benchmarks/manifest/split.json` |
| `freeze` | Records a SHA-256 hash of every benchmark and judge file (line endings normalized, `REVIEW.md` excluded) in `benchmarks/manifest/freeze.json` |
| `check` | Fails if anything frozen changed, appeared or disappeared; run before every test-set experiment |

Dev tasks may be used to tune prompts and retrieval. Test tasks are run only after `freeze`, for reported numbers.
Decision (2026-09-24): reviews continue while M1 and M2 are built; the freeze happens just before the Day 9 run.

## Statistics

`scripts/benchmark_stats.py` writes `docs/demo1/benchmark_stats/`: `tasks.csv` (one row per task), `summary.json`
and five charts (tasks by category and split, hidden checks per task, seeded bugs per task, bug generator outcome
by operator, prompt length).
