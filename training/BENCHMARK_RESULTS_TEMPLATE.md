# SVAGA model comparison: results template

All fields are placeholders. No evaluation results exist in this template.
TBD means not yet measured, NOT zero.

## Shared protocol (complete before running)

- Benchmark: Terminal-Bench 2.1, 89 planned tasks.
- Repository revision: 7131e4375048a0e408a8fb404b5f499d726b695b.
- Actual artifact/check-out identity: TBD.
- Harbor version / agent version / pipeline version: TBD.
- Model-serving stack and version: TBD.
- Sandbox type, image identities and resource limits: TBD.
- Model/tool/network access: TBD.
- Agent prompt/configuration hash: TBD.
- Per-task time, step and token budgets: TBD.
- Decoding settings, seeds, attempts per task: TBD.
- Concurrency: TBD (start infrastructure testing at 1).
- Infrastructure retry rule: TBD, fixed before scoring.
- Training package: openthoughts-expanded-10k-v1 (10,000 train / 1,000 validation candidates).
- Effective training records/tokens and processing policy per model: TBD.
- Dataset manifest/hash reference: TBD.
- Checkpoint selection rule based on validation: TBD.

## Summary

| Model slot | Condition | Exact model revision / adapter | Tasks evaluated / 89 | Attempts per task | Success rate | Infrastructure errors | Median trial duration | Raw results location |
|---|---|---|---|---|---|---|---|---|
| 1 | Base | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 1 | Fine-tuned | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 2 | Base | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 2 | Fine-tuned | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 3 | Base | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 3 | Fine-tuned | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 4 | Base | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 4 | Fine-tuned | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

For complete single-attempt evaluation: success rate = successful tasks / 89 x 100.
For repeated attempts: average each task's success frequency, then average across
the fixed task set. Record the retry/error policy and preserve failed attempts.
Do not silently exclude failed environment starts or turn retries into best-of-k.
Do not publish a full score while tasks remain unattempted.

## Per-model paired change

| Model slot | Base rate | Fine-tuned rate | Change in percentage points | Same settings? | Interpretation/limitations |
|---|---|---|---|---|---|
| 1 | TBD | TBD | TBD | TBD | TBD |
| 2 | TBD | TBD | TBD | TBD | TBD |
| 3 | TBD | TBD | TBD | TBD | TBD |
| 4 | TBD | TBD | TBD | TBD | TBD |

Change = fine-tuned percentage minus base percentage; this is not relative percent
improvement. Add paired uncertainty estimates when available; a small difference
from a single stochastic run is not proof of a reliable improvement.

## Per-trial record (repeat for each task and attempt)

- Run ID / task ID / attempt number / seed:
- Model and adapter identity:
- Official verifier raw reward and success decision:
- Status: success / task_failure / agent_timeout / infrastructure_error / not_run.
- Error type and evidence:
- Agent duration / total trial duration (state units):
- Input/output token usage if available:
- Retry relationship and reason, if any:
- Raw configuration, trajectory and verifier-log paths:

Do not paste API keys, private environment variables or hidden benchmark answers
into public reports. Keep raw evidence access-controlled.

## Training information from Kapil (not benchmark scores)

- Model/tokenizer revisions, quantization, LoRA settings:
- Package versions and hardware:
- Training/validation record counts and dataset hashes:
- Token-length handling and assistant-only loss-mask checks:
- Steps/epochs, effective batch size, supervised tokens, learning rate and seed:
- Training/validation losses, runtime and peak GPU memory:
- Checkpoint/adapter hash and successful fresh-process reload evidence:

## Required caveats in the report

The shared training corpus is repair-oriented, with unknown solution outcomes.
Text-overlap checks are not comprehensive semantic contamination clearance.
Task-group-separated validation is not repository-held-out validation.
Model comparisons using different pipelines cannot isolate fine-tuning effects.
Terminal-agent success is not a certification of application security or readiness.
