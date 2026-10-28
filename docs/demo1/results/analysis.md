# Demo 1 analysis

Source: `demo1`, 135 runs. 95% intervals: cluster bootstrap over tasks, 10,000 resamples.

| Metric | M0 plain prompt | M1 retrieval (RAG) | M2 spec-first |
|---|---|---|---|
| Passes every hidden check | 13% [0%, 29%] | 36% [18%, 56%] | 27% [13%, 42%] |
| Hidden checks passed (mean) | 73% [58%, 84%] | 84% [75%, 92%] | 73% [61%, 84%] |
| Broken among shipped apps (false assurance) | 82% [50%, 100%] | 53% [25%, 83%] | 60% [36%, 81%] |
| Runs that shipped a broken app | 31% [13%, 51%] | 20% [9%, 33%] | 33% [16%, 53%] |
| Correct among rejected apps (false rejection) | 11% [0%, 26%] | 29% [6%, 54%] | 10% [0%, 23%] |
| Seeded benchmark bugs caught by own tests | 0% [0%, 0%] | 1% [0%, 3%] | 40% [28%, 52%] |
| Own-app mutants caught by own tests | 29% [20%, 37%] | 41% [32%, 49%] | 21% [14%, 28%] |

## Paired comparisons (exact McNemar, same task and repeat)

| Pair | Outcome | Pairs | Only first | Only second | p |
|---|---|---|---|---|---|
| M0 vs M1 | passes all hidden checks | 45 | 1 | 11 | 0.0063 |
| M0 vs M1 | shipped broken app | 45 | 10 | 5 | 0.3018 |
| M0 vs M2 | passes all hidden checks | 45 | 4 | 10 | 0.1796 |
| M0 vs M2 | shipped broken app | 45 | 8 | 9 | 1.0 |
| M1 vs M2 | passes all hidden checks | 45 | 8 | 4 | 0.3877 |
| M1 vs M2 | shipped broken app | 45 | 6 | 12 | 0.2379 |

## Failed hidden checks by cause

| Cause | M0 | M1 | M2 |
|---|---|---|---|
| App did not start | 36 | 30 | 44 |
| Server crash (500) or no valid response | 54 | 22 | 83 |
| Accepts invalid or unknown input (2xx, expected 422) | 29 | 22 | 13 |
| Missing permission check (2xx, expected 403) | 3 | 4 | 8 |
| Missing conflict or state rule (2xx, expected 409) | 5 | 1 | 0 |
| Outside-service error not handled (expected 502) | 5 | 6 | 15 |
| Identity treated as validation (422, expected 403) | 7 | 2 | 0 |
| Rejects valid requests (4xx, expected 2xx) | 11 | 3 | 10 |
| Wrong response shape (missing key, wrong type) | 16 | 6 | 7 |
| Other wrong status code | 11 | 7 | 3 |
| Wrong value or state | 0 | 0 | 2 |

Note: a failed create often makes later checks fail with a missing key, so 'wrong response shape' includes cascades.

Charts: `charts/1_outcomes.png`, `2_headline_rates.png`, `3_pass_by_category.png`, `4_failure_taxonomy.png`.
