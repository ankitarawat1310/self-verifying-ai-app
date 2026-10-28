# Repair-action candidates v2

Prepared on 2026-10-24. These are unverified candidates, not an approved training release.

The original 10,000 training and 1,000 validation records remain unchanged in `../openthoughts-expanded-10k-v1/`.

## Results

| Measure | Train | Validation |
|---|---:|---:|
| Original tasks | 10,000 | 1,000 |
| Selected candidate tasks | 4,003 | 445 |
| No supported action | 5,287 | 541 |
| Reserved for a validation cluster | 389 | 0 |
| Additional members of an existing cluster | 321 | 14 |
| Token lengths reused from exact matching prior candidates | 3,325 | 354 |
| Token lengths still needed | 678 | 91 |
| Known to fit 4,096 tokens | 344 | 34 |
| Known to fit 8,192 tokens | 2,175 | 228 |

Length counts use the pinned Qwen3-Coder tokenizer recorded in report.json, not the small Colab pilot tokenizer. Unmeasured candidates are not counted as fitting.

## What changed

Selection now recognizes a deliberately narrow class of simple source-file sed substitutions. Test-only writes, unsupported edit formats, broad return replacements, known bad targets and immediate error/retraction signals are excluded from automatic selection. Unsupported does not mean useless or incorrect: those records require a different extractor or review.

Normalized task titles and edit fingerprints form duplicate clusters. Any cluster touching original validation is reserved for validation; no original validation task is moved into training. One candidate is selected per cluster. This grouping can miss semantic duplicates or group unrelated tasks, so zero shared cluster IDs is not proof of zero leakage.

Each candidate preserves preceding context and predicts one intermediate assistant action. It is not a complete secure application or a verified complete repair. Future observations are used only for filtering/audit, never included in that action's input.

## Verification and next step

Seven unit tests passed. Output checks confirmed disjoint train/validation cluster IDs, exclusion of the two known bad action targets, unchanged source hashes, and false approval/success flags throughout.

Next: measure the 769 new candidate lengths, review a small sample of candidate actions and their observed outcomes, then choose a documented pilot subset. Do not launch a full training run from these files yet. Preserve unknown outcomes explicitly; teacher claims of passing tests are not independent verification.

The smaller candidate count does not reduce or overwrite the original 10K collection. Recovering additional useful tasks requires broader extraction and quality review, not padding or duplicating these candidates.
