# SVAGA external evaluation choice

## Decision

Use Terminal-Bench 2.1 through Harbor for external terminal-agent evaluation.
The adjacent terminal_bench_2_1.json records 89 task IDs and the exact official
repository revision inspected. Do not silently replace this with a moving latest version.

Official sources:
- https://github.com/harbor-framework/terminal-bench-2-1
- https://www.tbench.ai/news/terminal-bench-2-1

## Keep the exam separate from training

Do not put these benchmark instructions, tests, oracle solutions or solution
trajectories in fine-tuning data, validation data or the SVAGA retrieval corpus.
Store any later benchmark checkout outside training data directories.
Evaluation agents receive only the task context permitted by the benchmark harness,
not hidden tests or oracle answers.

Before preparing the final training split:
1. Screen source metadata and task IDs against the pinned inventory.
2. Compare training task descriptions with benchmark instructions for exact and
   near duplicates. Review flagged similarities; matching vocabulary alone is not leakage.
3. Exclude confirmed overlaps and derived solutions, retaining an exclusion report.
4. Group copies of each training task together before splitting training/validation.

No overlap check has been completed yet. No claim of contamination-free data is made.
Public benchmarks may also have appeared in base-model pretraining, which we cannot
fully audit. Report this limitation.

## Later lab evaluation

Use the same pinned task set, agent harness, tool access, budgets and scoring rules
for all four fine-tuned models. Compare each with its own untuned base model when feasible.
Record model/tokenizer revisions, adapter hashes, Harbor version, generation settings,
attempt counts, environment failures, runtime and task success results.
Choose checkpoints on separate validation data, not this evaluation set.

First establish a supported isolated execution environment: the previous lab notes
reported Docker unavailable. No benchmark tasks or dataset commands were executed here.
Do not run untrusted task commands directly on the host.

Terminal-Bench measures broader terminal-agent ability. It does not certify complete
web applications as secure or production-ready, or directly isolate all four SVAGA
approaches. Keep application-specific checks as supplementary engineering evidence.

## Immediate next step

Prepare the data-overlap audit, then a small real-data training smoke test for Kapil.
The OpenThoughts 10K candidate remains unverified teacher-imitation data, not a
collection of 10,000 proven successful solutions. Do not infer success from null.

