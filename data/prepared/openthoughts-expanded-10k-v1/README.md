# SVAGA: 10K software-repair training candidate package

## What is this data?

This folder contains conversations showing an AI agent working on software bugs
in existing repositories. It is intended for supervised fine-tuning: a model learns
to produce assistant responses from examples of task requests and prior context.

These are **not 10,000 complete applications**, user-registration records, or
10,000 independently verified correct solutions. All selected task IDs belong to
the SWE-Smith source family within OpenThoughts-Agent-SFT-100K.

A conversation can contain a bug description, agent reasoning/plans, shell commands,
terminal output, inspected code, edits and testing attempts. Not every record has
all of these elements or a successful final test run.

## Files and counts

| File | Records | Purpose |
|---|---:|---|
| full.train.jsonl | 10,000 | Full training candidates |
| full.validation.jsonl | 1,000 | Separate validation candidates for monitoring training |
| pilot.train.jsonl | 100 | Small training-setup test, taken from full.train.jsonl |
| pilot.validation.jsonl | 20 | Small validation test, taken from full.validation.jsonl |
| manifest.json | Not a training dataset | Source revision, counts, exclusions, limitations and SHA-256 hashes |
| exclusions.audit-only.jsonl | 11,922 | Excluded-row identifiers and reasons; NOT training examples |

There are **11,000 selected examples in total**, not 11,120. The pilot records
are already included in the full files. Do not concatenate pilot and full files.

This folder supersedes the older openthoughts-10k-v1 package, which had 5,721
training and 644 validation records. Do not mix the two packages or their splits.

## How to understand one record

JSONL means JSON Lines: every non-empty line is one complete JSON object.
Here, one line contains an entire multi-message conversation, not one message.
Long conversations make these lines large; an editor may show only a preview.

| Field | Meaning |
|---|---|
| messages | Ordered conversation messages, each with a role and content |
| task | Original source task identifier |
| task_group | Identifier with the trailing copy suffix removed |
| source_row | One-based row number in the scanned source split |
| outcome | unknown for retained records |
| success_verified | false: independent successful completion is not established |

Messages marked assistant contain the agent's responses. In these exported traces,
messages marked user can also contain terminal feedback, not only a human request.
Some assistant responses include reasoning text and command JSON. Preserve this
distinction when designing chat formatting and training-loss masking.

Illustrative summary of an inspected record (not a standalone training example):

1. Request: fix broken HTML-comment handling in an existing Python library.
2. Feedback: a terminal run reports an UnboundLocalError.
3. Agent action: change where a variable is assigned.
4. Later feedback: the trace reports 178 tests passed and 1 skipped.

This is evidence recorded inside a trajectory. We did not independently rerun the
repository to certify that solution. A statement such as "all tests passed" from
the assistant alone is not a verification result.

## Source and selection

- Source: https://huggingface.co/datasets/open-thoughts/OpenThoughts-Agent-SFT-100K
- Exact source revision: 45fb28fcc38d352133cb28a1c8a43a2f14fea97b
- Source split: train. Our training/validation partitions were made from this split.
- Source records scanned: 22,922. The full upstream dataset was not scanned.
- Selection: deterministic source-order scan until 10,000 training and 1,000
  validation candidates were reached, with one selected example per task group.
- Split assignment: a deterministic hash of the task group, using seed text 3407.

Actual exclusion counts for THIS expanded package:

| Reason | Records |
|---|---:|
| Recorded execution error | 8,575 |
| Task group already selected | 3,240 |
| Assigned split had already reached its target | 107 |
| Total excluded | 11,922 |
| Total retained | 11,000 |
| Total scanned | 22,922 |

The earlier count of 3,634 error-labelled records belongs to the OLD 10K-source
package, not this expanded package. A recorded error can be an infrastructure
failure or timeout; exclusion does not establish that all its code was incorrect.

Because scanning stopped once the quotas were met, every selected example is
SWE-Smith-derived. This is a source-order software-repair subset, not a random or
balanced sample of all upstream task families.

## Checks completed and limitations

Completed checks include valid conversation structure, recorded-error filtering,
task grouping, exact-conversation deduplication, and benchmark overlap screening
for retained candidates. Final counts, file hashes, pilot membership, and the lack
of shared task groups or identical conversations across train/validation were checked.

The benchmark screen uses task IDs and instruction five-word-sequence overlap
against 89 pinned Terminal-Bench 2.1 instructions. It is a heuristic, not proof of
zero leakage: paraphrases, solution-only matches and base-model pretraining exposure
may be missed. Benchmark source revision:
7131e4375048a0e408a8fb404b5f499d726b695b.

Remaining limitations:

- No error label does NOT mean a correct solution. Retained outcomes are unknown.
- No independent replay or security certification has been performed.
- Task-group separation is NOT repository-level separation.
- Near duplicates may remain.
- Model-specific token lengths, chat templates and loss masking are not finalized.
- Full source-licence/provenance review remains outstanding.

## How this relates to the four SVAGA approaches

The same fixed dataset can be used to fine-tune four base models for a common
software-repair/terminal-agent comparison. It does not automatically provide
specialist supervision for all four approaches:

| Approach | What this package does and does not establish |
|---|---|
| RAG code generation | Supports code-work behaviour; explicit retrieved-context/code pairs are not established |
| Spec-first synthesis | Contains bug requirements; validated structured specification targets are not established |
| Neural test/invariant generation | Contains some assertions/testing activity; it is not a curated test/invariant-generation dataset |
| Counterexample-guided repair | Closest match; failure-to-patch evidence still needs per-record verification |

Use appropriate surrounding pipelines and evaluate claims honestly. This package
does not demonstrate generation of complete secure applications by itself.

## What to share with Kapil

Share this README, manifest.json, full.train.jsonl, full.validation.jsonl,
pilot.train.jsonl and pilot.validation.jsonl.

Do not load exclusions.audit-only.jsonl into a trainer. Never include benchmark
instructions, answers or anything under data/audits in training or RAG ingestion.
Name the intended train/validation files explicitly instead of loading every JSONL
file in a directory.

## Before running full training

Follow KAPIL_TRAINING_STEPS.md in this folder for the full lab checklist.

1. Confirm the four model and tokenizer IDs/revisions.
2. Count tokens using each model's chat template. Do not silently truncate examples.
3. Verify assistant-only loss masking and terminal-feedback handling.
4. Run the NEW pilot, save the adapter, reload it and test generation.
5. Record any formatting/filtering decision rather than silently changing this
   frozen candidate package. Agree on any common usable cohort if limits differ.
6. Use validation for model selection and keep Terminal-Bench separate for evaluation.

No model training was performed while creating this dataset package or README.
