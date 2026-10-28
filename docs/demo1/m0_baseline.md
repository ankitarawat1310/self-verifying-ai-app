# M0 baseline: evidence for 298-29

## What M0 is

M0 is the plain-prompt baseline. One LLM call writes the app and its own tests from the request and the public API contract. The app is accepted if its own tests pass. There is no retrieval, no policy and no other check.

## What was run

45 runs: 15 test tasks x 3 repeats, with Qwen3-Coder 30B (Ollama), on the frozen benchmark (frozen 2026-09-26, hash 5bf72116c6170a06). On average each run used 1 LLM call, about 4,460 tokens and about 48 seconds.

## Results

| Metric | M0 |
|---|---|
| Accepted / rejected | 17 / 28 |
| Passed every hidden check | 13% (6 of 45) |
| Hidden checks passed (average per run) | about 73% |
| Accepted but broken (false assurance) | 82% (14 of 17 accepted) |
| Rejected but actually correct (false rejection) | 11% (3 of 28 rejected) |
| Seeded benchmark bugs caught by its own tests | 0% |
| Bugs planted in its own app caught by its own tests | 29% |

## What it shows

- When M0 grades itself, ACCEPT means little: 14 of the 17 apps it accepted failed at least one hidden check.
- Every M0 rejection came from its own tests, because it has no other check.
- This is the reference point for M1 and M2. In the same runs M1 passed every hidden check in 16 of 45 runs against 6 of 45 for M0, the one difference in the Demo 1 results that is statistically significant (p = 0.006).

## Limits

Three repeats per task and one model. The 95% intervals are wide (for example, 13% fully correct has an interval of 0 to 29%).
