# Kapil: lab training checklist

## Goal and current status

Use the same fixed software-repair candidate dataset to fine-tune and compare four
base models. The dataset contains 10,000 training and 1,000 validation examples.
All selected examples are SWE-Smith-derived and have unknown final outcomes.
They are not certified correct solutions or four specialist datasets.

Data preparation is complete; model-specific training configuration is NOT complete.
No ready-to-run four-model training launcher is included in this folder.
Earlier dummy-data feasibility tests do not establish real-data readiness.

## 1. Receive the correct package

Copy these files to a dedicated lab data folder:

- full.train.jsonl: 10,000 examples.
- full.validation.jsonl: 1,000 examples.
- pilot.train.jsonl: 100 examples from full.train.jsonl.
- pilot.validation.jsonl: 20 examples from full.validation.jsonl.
- manifest.json, README.md and this checklist.

Do not combine the pilot with the full set. Do not combine this package with the
older openthoughts-10k-v1 package. Do not load exclusions.audit-only.jsonl or benchmark
audit material into the trainer. Use explicit file paths, not a directory-wide glob.

Check the received JSONL file hashes against manifest.json before use. On Linux,
run sha256sum followed by each file name; on PowerShell use Get-FileHash -Algorithm
SHA256 followed by each file path. Expect one conversation per non-empty line.

## 2. Check the lab machine and environment

Run in the lab terminal:

```bash
nvidia-smi
python --version
python -m pip show torch transformers datasets peft trl unsloth bitsandbytes
```

Record GPU model, VRAM, driver, Python and installed package versions. Missing
packages should be resolved through a compatible, version-pinned environment for
the chosen training stack, not by blindly upgrading the working lab environment.
Use a dedicated environment and one model run at a time initially.

Ankita's laptop has about 4 GB GPU memory and is not the proposed machine for the
20B-30B model runs. Use the lab hardware. If using Colab for a pilot, inspect the
allocated GPU first and save checkpoints persistently; a specific GPU/runtime is
not guaranteed. Do not change Windows settings or buy compute for this checklist.

## 3. Confirm the four models before configuration

Fill in the exact model ID and immutable revision, tokenizer revision, model
licence, quantization mode and supported sequence length for each run.

| Run | Exact model ID/revision | Tokenizer revision | Lab pilot status |
|---|---|---|---|
| 1 | To confirm | To confirm | Not run on this package |
| 2 | To confirm | To confirm | Not run on this package |
| 3 | To confirm | To confirm | Not run on this package |
| 4 | To confirm | To confirm | Not run on this package |

Previously inspected lab notes had three working dummy-training candidates and
an unresolved fourth candidate. Do not infer that all four are ready.
Prefer parameter-efficient fine-tuning if appropriate for the selected models;
LoRA/QLoRA support, target modules and memory use must be checked per architecture.

## 4. Inspect lengths and training formatting

For each tokenizer, apply its actual chat template and measure the full training
and validation sets WITHOUT truncation. Report median, p90, maximum token lengths,
and the number exceeding the proposed context window. File size or record count
alone cannot predict GPU memory use or training duration.

Use messages as the conversation field. Other fields are provenance, not text to
append automatically to the prompt. Terminal feedback may have role user. Some
assistant messages include reasoning text and shell-command JSON.

Verify on a decoded batch that:

- Conversation order and role boundaries are correct.
- Padding, user prompts, system messages and terminal feedback have ignored loss
  labels (commonly -100); intended assistant tokens receive loss.
- There is at least one supervised assistant span.
- Required task context and answer are not accidentally cut off.
- The policy for reasoning text and command formatting is explicit and consistent.

Do not silently shorten, drop, duplicate or repartition records. If examples do not
fit, discuss an explicit processing policy and preserve the original frozen files.
Any changed derived cohort needs a new manifest and honest effective counts.
Resolve remaining source licence/provenance concerns before full training.

## 5. Run the small real-data pilot first

Use pilot.train.jsonl and pilot.validation.jsonl. Suggested initial smoke test:
5-10 optimizer steps, per-device batch size 1, with gradient accumulation and other
memory settings chosen after the length check. This is a starting experiment,
not a guarantee that every model fits.

Record the model revision, complete configuration, effective batch size, sequence
length, supervised tokens, loss, elapsed time and peak GPU memory. Investigate
NaN/Inf loss, empty labels, out-of-memory failures and malformed batches.

Save the adapter/checkpoint AND tokenizer/configuration. Reload with the same base
model revision in a fresh process and generate a short answer to a held-out prompt.
Never execute generated shell commands directly on the host.

Pilot pass criteria: real optimizer updates, finite loss, validation runs, saved
artifacts reload, and generation works. This is only technical readiness, not proof
of code correctness, security or model improvement.

## 6. Start full training only after pilot review

Report the pilot results to the team before a long run. Use full.train.jsonl and
full.validation.jsonl with the agreed configuration. For comparable models, document
the shared data and budget policy and any architecture-specific differences.

Start each final experiment from its intended base model, rather than accidentally
continuing a pilot that has already seen some examples, unless that extra exposure
is deliberately included and reported in every model's budget.

Save resumable checkpoints in a new output folder for each model. Record dataset
hashes, seed, epochs/steps, learning rate, optimizer, LoRA settings, quantization,
precision, token budget, validation loss and runtime. Do not promise a full-run
duration until pilot throughput and token counts are measured.

Choose checkpoints using validation, NOT Terminal-Bench. Keep all validation data
out of optimizer updates. Training four models on identical repair data does not
by itself establish specialist RAG/specification/test-generation capabilities.

## 7. Return these artifacts to the team

- Exact base-model/tokenizer revisions and package versions.
- Training configuration and dataset manifest/hash references.
- Adapter/checkpoint plus reload instructions.
- Loss logs, GPU-memory measurements, duration and effective training counts.
- Before/after outputs on the same held-out prompts, clearly marked as examples,
  not independent correctness scores.
- Failures and any data-processing decisions.

Later, compare base and fine-tuned models through the same agent setup and pinned
Terminal-Bench 2.1 evaluation. Confirm a supported isolated runtime first: earlier
lab notes reported Docker unavailable. Benchmark execution is separate from this
fine-tuning checklist and must not run untrusted tasks directly on the host.
