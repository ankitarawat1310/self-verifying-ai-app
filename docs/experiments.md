# Experiment grid and metrics (Day 8)

`python scripts/run_grid.py --split dev --name smoke` runs every model on every task of a split. Each run is generated, checked by the model's own gate, scored by the hidden judge, and has its own tests run against the task's seeded bugs. Results go to `results/grid/<name>/`:
- one folder per run, holding the generated files, `verification.json`, `judge.json` and `record.json`;
- `summary.md`, `summary.csv` and `runs.csv` at the top level.

Re-running the same command resumes and skips finished runs. `--split test` refuses to start unless `freeze_benchmark.py check` passes.

**Budget, the same for every model:** 8 LLM calls, 40K tokens, 180 s of verification. Running out of budget or crashing is recorded as ERROR, never as ACCEPT.

## Metrics (`svaga_platform/app/experiments/metrics.py`)

| Metric | Meaning |
|---|---|
| Functional pass | The hidden judge passed every check. |
| Hidden / safety checks passed | Share of hidden checks passed (all, and safety only). |
| False assurance (of accepted) | Of the apps the model shipped (ACCEPT), the share that were broken. |
| Broken apps shipped | Of the broken apps, the share the model shipped anyway. |
| False rejection (of rejected) | Of the apps the model rejected, the share that actually passed everything. |
| Seeded bugs caught by own tests | Violation recall. The model's own test file is run on the reference app and on each seeded bug. A bug counts as caught only when a test that passes on the reference fails on the bug. |
| Excess imports | Modules beyond what the task needs. Network libraries count as excess unless the task calls an outside service. |
| Tokens, LLM calls, verification s, wall s | Cost. |

Each record also stores a `code_hash` of the pipeline code, so runs made with different code are never mixed by accident.

**Known limit:** M0 and M1 tests sometimes reach into their own app's internals (for example clearing a dict called `items_db`). Those tests fail on the reference app, so they can't catch anything. `recall_detail.tests_passing_on_reference` shows how many tests were usable.

## Smoke run 1 (`results/grid/smoke`, Sep 26, qwen3-coder:30b, 5 dev tasks x 1 repeat)

| | M0 | M1 | M2 |
|---|---|---|---|
| Accepted | 2/5 | 3/5 | 0/5 |
| Functional pass (all hidden checks) | 2/5 | 3/5 | 1/5 |
| Hidden checks passed | 74% | 94% | 75% |
| Shipped a broken app | 2 of 2 accepted | 0 of 3 | 0 |
| Rejected an app that was actually correct | 2 | 0 | 1 (a verifier bug, see below) |
| Own-app mutants caught by own tests (measured afterwards) | 0.14 | 0.50 | 0.34 |
| Benchmark bugs caught by own tests | 0.00 | 0.00 | 0.58 |

What it showed:
- **A verifier bug caused M2's one false rejection.** The contract check matched decorator text with a regex and missed `@ app.post(...)`. The expense app passed 14/14 hidden checks and was rejected. **Fixed:** the check now imports the app and reads its registered routes (method + path, ignoring path parameter names). The regex is only a fallback. This check is shared by M1 and M2.
- **"Benchmark bugs caught" is 0 for M0/M1 by construction.** Their tests import app internals (`from app import app, contacts_db`), so they can't even run against another app. It still shows that M2's spec tests are the only ones usable as an independent checker. For a fair comparison of test strength, I added the **own-app mutation score**: the same 6 bug operators seeded into each model's own app, scored by its own tests. On that, M1's tests (0.50) beat M2's spec tests (0.34), and M0's are weakest (0.14; 3 of its 5 test files fail on their own app).
- **M2 was strict** (no broken app shipped), but its generated apps were weaker than M1's on this sample. 3 of 5 accepted unknown body fields (`model_config` misplaced or missing) and 1 crashed on create. The spec tests caught all of these. Fixing them is M4's job (repair).
- **One sample per task is noisy.** The Day 9 run uses 15 tasks x 3 repeats.

## Demo 1 run (`results/grid/demo1`, Sep 26)

Setup: qwen3-coder:30b, 15 test tasks x 3 repeats x 3 models = 135 runs, 0 errors. All runs used the same code (code hash 5acf5839). The benchmark was frozen at 2026-09-26T18:15Z (hash 5bf72116c6170a06). **At freeze time the 7 AI-assisted REVIEW.md files still said "human confirmation pending".**

| | M0 | M1 | M2 |
|---|---|---|---|
| Functional pass (all hidden checks) | 6/45 (13%) | 16/45 (36%) | 12/45 (27%) |
| Hidden checks passed | 72% | 84% | 73% |
| Accepted | 17 | 17 | 25 |
| Broken among accepted (false assurance) | 14/17 (82%) | 9/17 (53%) | 15/25 (60%) |
| Correct apps rejected | 3/28 | 8/28 | 2/20 |
| Benchmark bugs caught by own tests | 0.00 | 0.01 | 0.40 |
| Own-app mutants caught by own tests | 0.29 | 0.41 | 0.21 |

### Where M2's false assurance came from (post-hoc breakdown, not a pre-planned analysis)

| M2 runs | Runs | Accepted | Broken among accepted |
|---|---|---|---|
| Connector tasks (the sandbox has no mock service, so spec tests skip the calls to the outside service) | 12 | 11 | 8 |
| Spec failed its checks twice, so M2 fell back to the interface-only skeleton | 11 | 7 | 5 |
| qwen spec passed its checks, non-connector task | 22 | 7 | 2 |

- M2 **fell back in 11/45 runs (24%)**. Three patterns:
  - approval tasks: qwen gave approve/reject both `not_self` and `owner_only`, so nobody could fire them;
  - `ticket_lifecycle`: `closed` marked terminal although a manager can reopen it;
  - `login_lockout`: the lock happens through `/login`, but qwen never attached transitions to it. The checker's hint only mentions create.

  qwen repeated the same mistake after one round of feedback.
- **The M2 gate accepted apps whose core behavior it had not tested:** connector happy paths are skipped, and fallback specs contain no state machine. That design gap produced 13 of its 15 false assurances.
- When M2 worked as designed (checked qwen spec, non-connector), it shipped 7 apps and 2 were broken. The sample is small and the subgroup was chosen after seeing the results, so treat this as a direction for M3/M4, not a result.

### Protocol note

These findings come from the test split. Changing M2 now and rerunning the same 15 tasks would tune on the test set. Planned use:
- Demo 1 reports this run as it is.
- The fixes are built on dev tasks for M3/M4 (Demo 2):
  - abstain instead of ACCEPT when a spec falls back or a core route went untested;
  - a local stub for the public mock-service contract in spec and property tests;
  - clearer checker feedback and 2 retries.
- Any rerun on these tasks is labelled post-hoc.

## Day 10: analysis and console pages

- `python scripts/analyze_grid.py results/grid/demo1` writes `results/grid/demo1/analysis/`:
  - `analysis.md`: headline table with 95% cluster-bootstrap intervals over tasks, exact McNemar paired tests, and failed hidden checks by cause;
  - `analysis.json`;
  - `failure_taxonomy.csv`;
  - 4 charts.

  A copy of the charts and `analysis.md` is in `D:\298B\demo1_charts\` for the slides.
- Paired tests on Demo 1: M1 passes all hidden checks more often than M0 (11 vs 1 discordant pairs, p = 0.006). No other difference is significant at 45 runs per model. For example, broken apps shipped, M1 vs M2: 6 vs 12, p = 0.24.
- Console, read-only API `svaga_platform/app/results_api.py`:
  - **Results** page (`/results`): run-set picker, headline table with intervals, the 4 charts, and a task x model grid of every run's outcome. Each cell shows the outcome in words and color plus hidden checks passed.
  - **Compare** page (`/compare`): one task and repeat, M0/M1/M2 side by side. Each column shows the model's own decision against the hidden result, failed hidden checks (functional or safety), own-gate failures, M2's spec source, and the generated files.
- Run the console as before (API on 8003, `npm run dev` in `model1_rag_generator/frontend`), then open http://localhost:5303/results.
