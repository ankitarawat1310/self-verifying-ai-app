# SVAGA: experiment history and handover to Kapil

> **Latest status — 26 October 2026:** Both Qwen2.5-Coder-1.5B and Qwen3-Coder-30B completed full 10K LoRA fine-tuning. The 1.5B supporting baseline reduced full dev1000 loss by 28.28%, with executable repairs 0/20 before and after. The 30B run and both of its development evaluations are complete. Full dev1000 prediction loss: 0.6508693448 to 0.2091027719 (67.87% reduction). Executable repairs: base 1/20 to adapter 4/20. Original artifact identity checks passed; strict numerical reload reproduction remains FAILED and unresolved. Current final handover: [KAPIL_30B_FINAL_HANDOVER_2026-10-26.md](KAPIL_30B_FINAL_HANDOVER_2026-10-26.md). External Terminal-Bench and the remaining required models are still pending. Older entries below are historical.


**Updated:** 26 October 2026, America/Los_Angeles  
**Project used:** `C:\repositories\self-verifying-ai-app-generator-clean`  
**Prepared for:** Kapil, from Ankita's completed Colab run and locally checked artifacts.

## Completed 30B development evaluation

The complete frozen paired experiment has 40 records: the original 20 pre-training base outputs, preserved unchanged, and 20 outputs from the saved trained adapter. No output hit the token cap. Each attempt ran in a fresh official Docker container with networking disabled and no host mounts.

| Metric | Base | Trained adapter |
|---|---:|---:|
| Fully passing repairs | 1/20 (5%) | 4/20 (20%) |
| Format accepted | 16/20 | 20/20 |
| Patches applied | 3/20 | 6/20 |
| Patches that did not apply | 13/20 | 14/20 |
| Applied patches that failed tests | 2/20 | 2/20 |
| Observed regression-test losses | 0 | 0 |

Four tasks passed only with the adapter, one passed only with the base, and 15 passed with neither. Thus the net improvement is three tasks / 15 percentage points, not universal improvement. Four base outputs were rejected as invalid diff format. No observed regression-test losses does not mean security or complete correctness: most generated patches never applied, and passing is limited to named functional tests.

All 20 task pairs passed clean/buggy/restored controls. One Trio task reproduces 18 of 21 upstream fail-to-pass labels; three already pass before repair. All named tests are still required for a successful candidate. The other 19 tasks reproduce all listed failures. The audit checked input/source hashes, raw generated patch bytes, per-stage JUnit outcomes, successful repair counts and the final summary (129 stages). It did not rerun tests or alter outputs.

Local evidence: `results/repair_eval/qwen3coder30b-paired-20261026/summary.json`, `analysis.md`, `verification.json`, `per_task_comparison.csv` and the full `reports.json`/per-attempt logs. The comparison is SWE-smith development evaluation with affected locations supplied, not Terminal-Bench, an untouched test set or complete secure-application validation. The dev100 loss reduction and strict numerical reload failure are separate results.

**Full dev1000 evaluation completed:** Both conditions cover the same 1,000 tasks / 332,113 target tokens in one loaded model instance. The downloaded report was locally audited for identity, task order, target counts and summary arithmetic; native tokenization was independently regenerated on CPU and its input digest matched. Base loss 0.6508693447994254; adapter loss 0.20910277191314444; reduction 67.87331073679889%. Evidence: `results/fine_tuning/qwen3coder30b-full-dev1000-20261026`. No optimizer updates. This new same-instance protocol does not resolve the earlier strict cross-reload numerical failure. The 30B experiment handover is complete; see the final handover document above.

## 1. Earlier completed 1.5B baseline in plain language

We prepared a fixed dataset containing **10,000 training examples plus 1,000 development-validation examples** and completed one full fine-tuning run on **Qwen/Qwen2.5-Coder-1.5B-Instruct**.

The model learns to read an issue and supplied buggy Python code, then predict a repair as a unified diff. On the same 1,000 validation examples, prediction loss fell from **0.4616815888 to 0.3311282826**, a **28.28% relative reduction**.

The adapter was saved, reloaded, evaluated, and downloaded. This is a completed small-model training baseline. **The generated-repair development comparison is now complete: base 0/20 fully passing repairs; adapter 0/20. Three adapter patches applied, but failed tests. Terminal-Bench evaluation and all four required specialist models/approaches remain incomplete.**

Historical next step at the end of the 1.5B run was the larger-model preflight, which has since been completed together with the 30B run. Preserve this earlier baseline and its patch failures. The 1.5B baseline is not one of Kapil's four previously recorded lab candidates; count it toward the final comparison only if the team explicitly chooses to do so.

## 2. How we reached this dataset

1. We inspected OpenThoughts agent trajectories and prepared earlier samples/pilots. Many records had unknown outcomes; assistant statements such as “all tests passed” were not accepted as independent proof.
2. Full terminal conversations were long. In the original 10K collection, none fit 2,048 tokens, only five fit 4,096 tokens, and 436 fit 8,192 tokens with the inspected tokenizer. A long-example training attempt ran out of memory on the T4.
3. We tested training, save, reload, and validation using tiny pilots. A later 160-training/8-validation terminal-action pilot also ran, but its results are a separate experiment on different data.
4. We changed the main training source to official **SWE-smith Python tasks**, rather than using uncertain terminal conversations as if they were verified successful repairs.
5. Initial patch-only examples lacked sufficient surrounding code and had uneven repository coverage. Version 2 supplies whole affected functions and selected supporting context, and balances selection across repositories.
6. We froze the current package, trained the 1.5B model on all 10,000 training examples, and evaluated both base and trained adapter on the same 1,000 development examples.

**The current dataset is SWE-smith-derived localized Python repair data. It is different from the earlier `openthoughts-expanded-10k-v1` collection.**

## 3. Final dataset to use and share

**Folder:** `C:\repositories\self-verifying-ai-app-generator-clean\data\prepared\swesmith-context-repair-10k-v2`  
**Upload/share ZIP:** `C:\repositories\self-verifying-ai-app-generator-clean\data\prepared\swesmith-context-repair-10k-v2.zip`

| Item | Final value |
|---|---|
| Upstream source | `SWE-bench/SWE-smith-py` |
| Pinned source revision | `77cab9055d42ab4a5c25c89a8f937096db13558e` |
| Source rows inspected during preparation | 50,908 |
| Training file | `train.jsonl`: 10,000 records; 10,000 distinct instance IDs |
| Development-validation file | `validation.jsonl`: 1,000 records; 1,000 distinct instance IDs |
| Training repositories | 119 repository identities |
| Validation repositories | 12 repository identities |
| Exact cross-split task/repository/patch/input overlap | 0, according to preparation checks |
| Largest training repository contribution | 161 examples, or 1.61% |
| Largest validation repository contribution | 104 examples, or 10.4% |
| Longest training example | 4,094 tokens with the pinned 1.5B tokenizer |
| Longest validation example | 4,096 tokens with the pinned 1.5B tokenizer |
| Supervised answer tokens | 3,389,665 training; 332,113 validation |
| Package status | `experimental_training_package_not_verified_repair_corpus` |

Validation is **additional** to the 10K training set: 11,000 examples in total. Validation examples did not go through optimizer updates. They have now been inspected/evaluated repeatedly and are a development set, not an untouched final test set.

### What is inside one record?

Each JSONL line is one JSON object. Important fields include:

- `instance_id`, `repo`, `image_name`, and `source_revision`: identify the upstream task and environment.
- `messages[0]`, role `user`: issue description, supplied affected file locations, buggy functions, and supporting Python context.
- `messages[1]`, role `assistant`: target repair as a unified diff.
- `tokens`, `context_files`, `context_method`, and source/patch hashes: document preparation.
- Upstream FAIL_TO_PASS/PASS_TO_PASS counts and local-review flags: provenance, not a claim that every record was independently replayed.

Illustrative example only:

```text
Input: The function subtracts instead of adding.
       def add(a, b):
           return a - b

Target: a unified diff changing return a - b to return a + b.
```

A row teaches one code repair; it does not represent a complete secure application. File locations are supplied, so repository search/localization is outside this training task.

### Patch direction matters

The official source patch **introduces the bug**. We reconstruct the buggy code and use the **reverse patch as the repair target**. Using the original patch as the answer would teach bug introduction.

Targets normalize diff formatting, remove Git blob-hash lines and trailing hunk function labels, and place deleted lines before added lines. Inputs are built from buggy source rather than the correct pre-bug file or the bug-introducing diff. Source hashes are used by preparation checks, not as answer text.

### Integrity values

```text
train.jsonl SHA256:
36d790d8f87c19cf2d914863cb8a3be7c1be3c2e74d5af183fd3755b0a802eec

validation.jsonl SHA256:
3953a213500952e1b03f003514d36b2b5c6c661ed5a387cbc278d7d588fd02dc

swesmith-context-repair-10k-v2.zip SHA256:
b55b143fc41ec5dd35e1aca897168a293b83e6d83ecc698973d79318519fe3fd
```

Source metadata and per-repository licensing should travel with any redistributed data; this handover does not establish a blanket license for every upstream repository.

## 4. Dataset checks completed

- Verified source context for all **11,000 records**, covering **76,356 context blocks**, against official Git blob information.
- Checked selected patch application and restoration to clean source blobs for **20 examples**. These are source-integrity checks, not executable model-repair tests.
- Checked exact train/validation task, repository, patch, and input overlap.
- Verified token limits with the pinned Qwen 1.5B tokenizer; no training-time truncation was used.
- Used exact-ID/instruction 5-gram screening against a pinned Terminal-Bench inventory, and prior-validation title screening during preparation. These are heuristics; they do not prove absence of semantic duplicates or contamination.
- Preserved exclusions, preparation reports, and reference replay evidence.

Most records have not been behaviorally replayed locally. Human review/sign-off for every example is not claimed. Existing per-record flags should not be changed to “verified” merely because preparation completed.

## 5. Executable reference-repair checks

Five selected source tasks were reconstructed in isolated official environments. For each: clean source passed the listed tests; the official bug patch caused a failure; reversing that patch restored the tests.

| Source project | Clean baseline | After introducing bug | After reference repair |
|---|---:|---:|---:|
| OAuthlib | 673 passed | 672 passed, 1 failed | 673 passed |
| Iniconfig | 28 passed | 27 passed, 1 failed | 28 passed |
| Funcy | 203 passed | 202 passed, 1 failed | 203 passed |
| Typeguard | 456 passed | 455 passed, 1 failed | 456 passed |
| Schema | 116 passed | 115 passed, 1 failed | 116 passed |

These validate selected source tasks and reference patches. **They are not five successful repairs generated by our trained adapter.** Typeguard and Schema are documented additional checks of actual current training records. The earlier three checks were also used for the small replayed-pairs preparation.

Evidence is under `C:\repositories\self-verifying-ai-app-generator-clean\data\audits`, in the named `*-replay-20261025` directories. Successful Iniconfig and Typeguard replays are in `attempt-2`; earlier failed attempts were retained. Separate bytecode directories avoided stale Python cache results, and the Typeguard environment needed the correct interpreter/tool PATH.

## 6. Model and training configuration actually used

| Setting | Completed run |
|---|---|
| Base model | `Qwen/Qwen2.5-Coder-1.5B-Instruct` |
| Pinned model revision | `2e1fd397ee46e1388853d2af2c993145b0f1098a` |
| GPU | Google Colab Tesla T4, as reported in the runtime |
| Method | QLoRA: frozen 4-bit base plus trainable LoRA adapters |
| Quantization | NF4; double quantization; float16 compute |
| LoRA rank / alpha / dropout | 8 / 16 / 0.05 |
| Target modules | `q_proj`, `v_proj` |
| Trainable parameters | 1,089,536, approximately 0.0705% of total parameters |
| Optimizer | AdamW; learning rate 0.00002; weight decay 0 |
| Microbatch / gradient accumulation | 1 example / 8 microbatches |
| Epochs / optimizer updates | 1 / 1,250 |
| Seed | 42 |
| Loss masking | Input/prompt tokens masked; repair-answer tokens contribute to loss |
| Memory measures | Gradient checkpointing, float16 mixed precision, gradient clipping |
| Observed peak training allocation | 10.7716 GiB; this is PyTorch allocated peak, not total GPU capacity |
| Checkpoint interval | Update 1, then every 50 updates, and final update |

Recorded software: PyTorch `2.11.0+cu130`, Transformers `5.20.2`, PEFT `0.21.2`, Accelerate `1.15.0`, bitsandbytes `0.50.2`. The user-reported Colab Python version was `3.13.16`.

QLoRA updates the adapter parameters; we did not train a foundation model from scratch or update every base-model weight. Quantization makes the frozen base smaller in memory. One epoch means each of the 10,000 training examples was used once. Accumulation of eight explains 10,000 / 8 = 1,250 optimizer updates.

## 7. Observed results and their meaning

| Evaluation | Before | After | Absolute change | Relative loss reduction |
|---|---:|---:|---:|---:|
| Fixed 100-example development subset | 0.4910578743 | 0.3597958797 | -0.1312619946 | approximately 26.73% |
| Full 1,000-example development set | 0.4616815888 | 0.3311282826 | -0.1305533062 | **28.2778%** |

The same examples and answer-token counts were used on both sides of each comparison. The full comparison covers **332,113 supervised answer tokens** per model. Loss is token-weighted cross-entropy: lower means better prediction of the recorded repair text.

The saved-adapter reload check matched the saved **100-example** evaluation exactly: absolute loss difference **0.0** on the same loaded quantized base. This check does not constitute a full fresh-base reload test across every hardware/software configuration.

What the results support:

- The full 10K training/save/evaluation workflow ran.
- The adapter predicts reference repair text better on this development set than the same quantized base without the adapter.
- The saved adapter can be reloaded for evaluation.

What they do not establish:

- 28.28% repair accuracy, a 28.28 percentage-point success gain, or 28.28% more secure applications.
- Executable correctness of generated patches, regression freedom, or permission/security guarantees.
- Terminal-Bench/Harbor performance or superiority over Kapil's larger models.
- Statistical robustness across multiple seeds or an untouched final benchmark.
- Completion of all four required fine-tuned models/approaches.

An earlier terminal-action pilot produced plausible repair text but incorrect sequential `sed` replacements in a string simulation. That is a concrete reason to evaluate execution, rather than treating lower text loss as correctness. It is historical pilot evidence, not a measured failure rate for this final diff-prediction adapter.

## 8. Saved artifacts and what to give Kapil

### Current model export

**Verified local extracted copy:**  
`C:\repositories\self-verifying-ai-app-generator-clean\results\fine_tuning\qwen15b-context-10k-v2`

It contains:

```text
adapter/
    adapter_model.safetensors
    adapter_config.json
    README.md
tokenizer/
    tokenizer.json
    tokenizer_config.json
    chat_template.jinja
results.json
full_development_comparison.json
reload_check.json
dataset_manifest.json
```

**Preferred downloaded ZIP:** `C:\Users\ankit\Downloads\SVAGA_Qwen15B_10K_Final.zip`  
SHA256: `26cc0b1516895beb4a36bacdd7ff6e40e22ee06965ffde7c7a476d3210d6971d`

The earlier `svaga-localized-qwen15b-10k-final.zip` contains identical shared files but lacks `full_development_comparison.json`. Use the newer ZIP for handover. The ZIP contains a small adapter, not all 1.5B base weights. Load it with the exact base model and revision above; the adapter config itself has a null revision field, so obtain the pin from the result/manifest rather than guessing.

### Google Drive copies

```text
/content/drive/MyDrive/SVAGA/context-qwen15b-10k-v2/final_export
/content/drive/MyDrive/SVAGA/context-qwen15b-10k-v2/step-01250
```

The final export is for inference/evaluation. Full checkpoints also contain training state; the export ZIP is not a complete optimizer-resume snapshot. Preserve the Drive checkpoints until the team has verified its backups. Runtime disconnection removes temporary Colab memory, not these Drive files or downloaded ZIPs.

### Share these items

1. Current dataset ZIP, including its manifest.
2. Newer final adapter/export ZIP.
3. This handover file and `C:\repositories\self-verifying-ai-app-generator-clean\training\handover-evidence-2026-10-25.json`.
4. Current Colab notebook and runtime source from the repository.
5. Lab references and replay/audit reports when Kapil needs to inspect provenance or reproduce checks.

The repository notebook is `C:\repositories\self-verifying-ai-app-generator-clean\training\notebooks\SVAGA_10K_Context_Repair_Qwen15B_v2.ipynb`. Its original final optional cell evaluates the trained adapter on 1,000 examples only. The **paired base-versus-adapter 1,000-example comparison was run in an additional Colab cell** and is preserved in the downloaded report. Keep/download the actual completed Colab notebook as well; do not assume the local starter notebook contains every extra recovery/evaluation cell.

The machine-readable handover evidence file was checked against the local dataset and newer export ZIP. Its paths should be adjusted if Kapil uses a different checkout location.

## 9. External benchmark and the four-approach requirement

Training source: SWE-smith-derived repair examples.  
Planned external evaluation: **Terminal-Bench 2.1 through Harbor**.

The project records **89 task IDs** at repository revision `7131e4375048a0e408a8fb404b5f499d726b695b`. This is the pinned project inventory, not a claim about the latest upstream release. Instructions, hidden tests, oracle solutions, and trajectories from final benchmark tasks must stay out of training, development validation, and the retrieval corpus.

No Terminal-Bench score has been produced for this adapter. A patch-prediction adapter also needs a compatible agent/tool interaction layer before it can solve end-to-end terminal tasks through the harness. Local SWE-smith reference replay is training-data validation, not a replacement benchmark.

| Required approach | Current work supports | Work still needed |
|---|---|---|
| Retrieval-augmented code generator | Existing SVAGA retrieval infrastructure; general code-repair baseline | Define explicit retrieved-context supervision and evaluate the fine-tuned generator in that pipeline |
| Spec-first program synthesis | Issue text and code-repair experience | Prepare/validate structured specification targets and train/evaluate the spec-first stages |
| Neural test and invariant generator | Upstream test metadata and replay infrastructure | Prepare real test/property-generation targets and evaluate their defect detection |
| Counterexample-guided repair agent | Buggy-code-to-diff training is a useful building block | Include appropriate failure evidence, execute generated repairs, and evaluate a bounded repair loop |

Four base models and four system approaches are different choices. Training four different checkpoints on the same repair data does not by itself implement all four approaches. M0/M1/etc. remain system configurations, not foundation-model identities.

## 10. Kapil's recorded larger-model lab observations

These are existing **dummy-data capacity/timing observations**, not real-10K training results or guarantees for another GPU/runtime. Peak values below retain the original report's `peak_gpu_gb` units and should not be compared as exact GiB values with the T4 allocation above.

| Recorded candidate | Successful dummy sequence lengths observed | Recorded limitation |
|---|---|---|
| `Qwen/Qwen3-Coder-30B-A3B-Instruct` | 16,384 and 24,576 | 32,768 failed with negligible memory available for fused cross-entropy |
| `Qwen/Qwen3.6-27B` | 2,048 through 16,384 | No real current-dataset preflight completed in these records |
| `unsloth/gpt-oss-20b-unsloth-bnb-4bit` | 2,048, 4,096 and 8,192 | 16,384 failed with negligible memory available for fused cross-entropy |
| Devstral Small 2 24B, Mistral/Unsloth variants recorded | No successful training length established | Meta-tensor loading/training setup error at the 2,048-token attempt |

Lab artifacts remain in `C:\repositories\self-verifying-ai-app-generator-clean\training\lab_reference`. These observations suggest candidates for further preflight; they do not select the final model or prove that a larger model fits the current Colab T4. The 1.5B adapter cannot be attached to a differently sized/architected model.

## 11. Next steps and suggested ownership

### A. Preserve and evaluate the completed baseline — Ankita / Kapil

1. Verify the dataset and export hashes after transfer. Keep the original frozen files unchanged.
2. Keep the completed notebook, export, paired 1,000-example report, and Drive checkpoint backups.
3. Generate patches with the base and adapter for a fixed development task list, using identical decoding and token budgets. Save raw outputs and task IDs.
4. Check diff parsing/application, then execute tests in the matching isolated official task environments. Separate format failures, non-applying patches, failed fixes, and regressions. Do not execute arbitrary output on the host.
5. Report both text loss and executable outcomes. Distinguish reference-patch replay from generated-patch success.

### B. Start a larger-model experiment — Kapil in the lab, or Ankita after hardware selection

1. Agree on the exact model ID, pinned revision, actual available GPU/VRAM, method, runtime versions, and compute budget. Do not select by dummy fit alone or assume the T4 supports every candidate.
2. Re-tokenize the **same raw messages** with the chosen model's tokenizer/chat template. The current <=4,096 counts belong to the 1.5B tokenizer. Check answer boundaries and prompt masking again.
3. If examples no longer fit, choose a supported context limit or make an explicitly versioned data transformation and report exclusions. Do not silently truncate targets or replace the frozen dataset.
4. Run a small real-data preflight, including long examples: load, forward pass, backward pass, optimizer step, save/reload, and validation. Record memory and seconds per step before committing to 10K.
5. Create a fresh adapter with architecture-appropriate target modules, compatible quantization/attention settings, and a **new output/checkpoint directory**. Do not overwrite the 1.5B run or reuse its optimizer state.
6. For a controlled first comparison, preserve task IDs, split assignments, epoch/exposure budget, input context policy, and evaluation task list; record any necessary differences. Sequence lengths, batch/accumulation, learning rate and total compute must all be reported.
7. Estimate total time from measured real-data throughput. Schedule checkpoints and persistent storage. This handover contains no validated larger-model ETA.
8. After the full run, evaluate base and trained model on the same development examples; save raw reports and generate/test repairs. Use external benchmark results separately.

`C:\repositories\self-verifying-ai-app-generator-clean\training\check_model_token_lengths.py` is a legacy audit helper whose CLI expects `full.train.jsonl`/`pilot.train.jsonl` names. It must be adapted or replaced for the current `train.jsonl`/`validation.jsonl` package before use. Do not run it against the current folder assuming it already supports these filenames.

## 12. Repository cleanup and historical notes

- Earlier cleanup removed approximately **2.05 GiB** of obsolete exports and generated caches.
- Removed 37 superseded scripts/tests/notes from the active training folder, preserving them in a history ZIP.
- Removed five leftover deployment-test output files.
- Preserved application source, current datasets, source-blob cache, lab files, replay reports/logs/XML, current retrieval index, and Demo 1 results.
- Checked the remaining training imports, notebook generation, and four overlap unit tests. The full project suite was not rerun for these artifact-cleanup operations.
- Notebook generation and packaging defaults now point at the current context-v2 dataset.

Cleanup records and historical ZIPs are under `C:\repositories\self-verifying-ai-app-generator-clean\data\audits\cleanup-20261025`.

The checkout still reports `fatal: this operation must be run in a work tree` for Git status. Cleanup did not modify Git metadata or commit/push the handover. Resolve this separately before relying on a Git check-in; there is no need to delete source or research artifacts to address that error. Runtime `results/` and ZIPs are ignored by the existing Git rules, so share model/data artifacts deliberately rather than assuming a normal push includes them.

Some older preparation reports still say `training_started: false`, and the starter notebook mentions three source replays. Those are historical snapshots. This handover and its evidence JSON record the later completed 10K run and all five reference replays; original manifests were preserved unchanged to retain their hashes. Those earlier flags must not be interpreted as “no training happened,” nor should they be edited to claim full behavioral verification.

## 13. Short handover message

> We completed one full QLoRA run of Qwen2.5-Coder-1.5B-Instruct on the final SWE-smith context-repair v2 dataset: 10,000 training examples plus 1,000 development-validation examples, with repository-separated splits. Full validation loss fell from 0.46168 to 0.33113, a 28.28% relative reduction. The adapter, tokenizer, reports, and dataset hashes are saved. Five source reference tasks were replayed successfully. The later one-shot comparison on 20 development tasks produced 0/20 fully passing repairs for both base and adapter; three adapter patches applied but failed tests. Next we should inspect the patch failures and run a real-data hardware/tokenizer and generation preflight for a larger model. The four required specialist approaches and Terminal-Bench evaluation remain to be completed.


## 14. Development repair comparison prepared after this handover

The next evaluation is now implemented. A deterministic round-robin sample freezes **20 existing validation tasks across all 12 validation repositories**, with no selection based on model outputs. This is a development sanity check, not a new external benchmark. The training and validation files above are unchanged.

**Colab notebook:** `C:\repositories\self-verifying-ai-app-generator-clean\training\notebooks\SVAGA_Repair_Dev20_Base_vs_Adapter.ipynb`  
**Prompt-only upload ZIP:** `C:\repositories\self-verifying-ai-app-generator-clean\data\evaluation\repair-dev20-v1\repair-dev20-prompts.zip`  
**Local private metadata:** `C:\repositories\self-verifying-ai-app-generator-clean\data\evaluation\repair-dev20-v1\private_tasks.jsonl`

In a fresh Colab GPU runtime, upload the new notebook and run its cells in order. When asked for two ZIPs, provide only the prompt packet and `SVAGA_Qwen15B_10K_Final.zip`. Keep private metadata on the local execution machine. The notebook verifies adapter/tokenizer hashes and generates **40 outputs**, one base and one adapter output for each frozen task, with greedy decoding and a 2,048-new-token cap. It creates no optimizer, performs no training, and does not execute generated code. Progress is saved after each output to:

```text
/content/drive/MyDrive/SVAGA/repair-dev20-qwen15b-v1/generation_results.json
```

Download that JSON when complete. Start Docker Desktop in Linux-container mode on the execution machine. Run one task before the full comparison; replace the predictions path if the browser renamed the download:

```powershell
cd "C:\repositories\self-verifying-ai-app-generator-clean"
python -B training/run_repair_eval.py --predictions "C:\Users\ankit\Downloads\generation_results.json" --limit 1 --pull-missing
```

`--pull-missing` explicitly allows potentially large official image downloads. Omit it to use installed images only. After the one-task environment controls work, run the frozen full comparison:

```powershell
python -B training/run_repair_eval.py --predictions "C:\Users\ankit\Downloads\generation_results.json" --limit 20 --pull-missing
```

Each task/variant uses a fresh disposable container with no host mounts or network access, two CPUs, a 4 GB memory limit and restricted capabilities. It checks clean tests, buggy tests and reference-restored tests before scoring the generated repair. Private input/oracle patch files are removed before generated source executes. This isolation is not a formal anti-cheating or security guarantee.

The runner records diff-format validity, patch application, restored FAIL_TO_PASS tests, preserved PASS_TO_PASS tests, generation time, image IDs, logs and JUnit evidence. Invalid environments remain visible and are excluded from paired model-success comparisons; no replacement tasks are silently selected. Mido's upstream `../dev/tests/` selectors have one explicitly recorded repository-specific mapping to `tests/`; file existence and all reference controls must still pass.

Outputs go to a new directory under `C:\repositories\self-verifying-ai-app-generator-clean\results\repair_eval`. GPU generation and the full frozen Docker comparison are now complete. Final paired results cover all 20 tasks; see Section 16 for the preserved compatibility checks and final evidence. The paths below identify the current evidence. Do not report implementation/synthetic test passes as model repair successes.


## 15. Generation and original Docker comparison history

All 40 outputs were downloaded and verified against the frozen prompt packet and adapter artifacts. The verified copy is:

`C:\repositories\self-verifying-ai-app-generator-clean\results\repair_eval_inputs\repair-dev20-v1\generation_results.json`

SHA256: `24fd1d67ef76b89faf3af1af7051a82c08801d0ab61f8387c9dd06e0f7dec2ea`.

The base produced 6,535 output tokens in approximately 418.3 seconds; the adapter produced 6,855 in approximately 535.9 seconds. One adapter output hit the 2,048-token cap; no base output hit it. These are recorded generation timings, not controlled hardware-throughput benchmark results. Token-limit outputs are retained, not regenerated.

The initial preflight exposed two evaluator compatibility issues before any model repair was scored:

- Native Git accepts traditional old-file `.orig` labels with timestamps. The validator now accepts those labels for the same permitted target file, without rewriting model outputs. A locally authored Git check and regression tests document this.
- The first Trio task lists 21 upstream FAIL_TO_PASS tests, but only 18 fail in the local official image; three already pass. Protocol `repair-dev20-execution-v2` records this difference and credits only failures actually observed. Clean/reference-restored states must pass all named tests, every listed PASS_TO_PASS control must remain passing in the buggy state, and the generated repair must pass all named tests. Strict upstream failure reproduction is reported separately.

The original invalid preflight and evaluator sources remain preserved. The corrected preflight checked all **729 named tests** in the first task's reference states. Its base-model patch did not apply; its adapter output was capped. Neither is counted as a successful repair.

Full comparison location:

`C:\repositories\self-verifying-ai-app-generator-clean\results\repair_eval\repair-dev20-full-v2-20261025`

Read `summary.json` and `reports.json` there for the preserved original v2 results (18 valid task pairs before compatibility checks). They are saved after each variant. The frozen task list and raw model outputs are unchanged, and no tasks are silently replaced if images/reference environments fail. The implementation checks now cover 27 tests. The final comparison is now complete; use the combined results in Section 16 rather than treating the original 18-task coverage as final.


## 16. Final executable development results — 26 October 2026

The interrupted run resumed from its 18 saved variant records; training and the 40 GPU generations were not repeated. The original evaluator source hashes were checked before continuing. The final comparison covers **20 paired, reference-valid tasks across 12 repositories**, with one original generated output per model per task.

| Metric | Base model | Fine-tuned adapter |
|---|---:|---:|
| Generated outputs | 20 | 20 |
| Patches applied to the buggy repository | 0 | 3 |
| Fully passing repairs | **0/20** | **0/20** |
| Patch application failures | 20 | 16 |
| Applied patches that failed tests | 0 | 3 |
| Generation token-limit failures | 0 | 1 |
| Applied-patch cases introducing regression-test failures | Not applicable: no patches applied | 1 |

All three applied adapter patches fixed **none of the observed failing tests** in their respective tasks. One also reduced passing regression controls from 11/11 to 3/11. This shows why patch application and lower prediction loss are insufficient readiness criteria.

Most failures were invalid diff hunk structure/counts or edits whose context did not match the actual buggy file. No hunk counts, generated source, outputs or tasks were rewritten to make them pass. No iterative repair loop was used. These are one-shot patch-generation results on a small development sample; they do not prove that every use of these models fails.

### Evaluator compatibility evidence preserved

1. **Original v2 run:** 18 valid task pairs; two Stackprinter tasks were blocked by an initial-image cleanliness guard. Original reports and code hashes remain unchanged.
2. **Packaging metadata compatibility:** Read-only inspection found only four preinstalled text files in `stackprinter.egg-info`. A supplementary adapter accepts and hashes such installed metadata, still rejecting tracked modifications, unexpected files and executable content. It preserves the original source/blob/test checks. Both affected tasks then had valid controls.
3. **Native Git path compatibility:** Git-prefixed diffs require `-p1`; plain source paths require `-p0`. Ten outputs with a unique plain-path convention were rechecked with the strip level determined solely by their raw headers. Standard `.orig` old-file labels and timestamps are accepted. No output was rewritten and no levels were tried until one passed. The capped output and an ambiguous mixed-prefix output retained their original failure classifications. These checks did not yield additional passing repairs.
4. **Upstream failure metadata:** 19 tasks reproduced every listed FAIL_TO_PASS failure. The first Trio task reproduced 18 of 21; three already passed. Only observed failures can receive fix credit, while every named test must pass for full repair success.

### Canonical combined artifacts

Final result directory:

`C:\repositories\self-verifying-ai-app-generator-clean\results\repair_eval\repair-dev20-native-path-compat-20261026`

- `summary.json`: final counts, scope and compatibility notes.
- `combined_reports.json`: all 40 final variant records, including reference and candidate test outcomes.
- `per_task_comparison.csv`: 20 paired task rows for analysis.
- `verification.json`: integrity and completion checks.
- `provenance.json`, `evaluator-sources/`, per-attempt logs/XML: supplementary path-compatibility evidence.

The original v2 run remains under `repair-dev20-full-v2-20261025`, and the packaging-only supplementary run remains under `repair-dev20-metadata-compat-20261026`. Keep these with the canonical combined directory when auditing/reproducing the result. The combined reports reuse unchanged earlier outcomes where no compatibility change was needed; they are not a claim that every model passed or that all variants were rerun unnecessarily.

The original training loss result remains valid: full development loss improved by 28.28%. **That improvement did not translate into a fully working repair on this frozen sample.** We can report successful fine-tuning optimization and completed evaluation, but not demonstrated functional improvement or production readiness.

For the larger-model phase, first measure actual GPU capacity/token lengths and run a short real-data training/save/reload check. Also generate and execute sample patches before committing to a full 10K run. Reuse this frozen development comparison and keep Terminal-Bench/Harbor separate as the planned external evaluation. The four specialist approaches still require their own justified training targets and system integration.


## 17. Separate SEARCH/REPLACE pilot — inference only

A controlled inference-format experiment was prepared and has now completed; see Section 18 for results. It uses the **same 20 task IDs/order, byte-identical issue and buggy-source bodies, same pinned Qwen base and 10K-trained adapter, same greedy decoding and 2,048-new-token budget**. Only the output-format instructions change. The original dataset, adapter, generations and 0/20 unified-diff results remain unchanged.

Instead of predicting diff line numbers and hunk lengths, the model names a supplied file and emits:

```text
src/example.py
<<<<<<< SEARCH
    return a - b
=======
    return a + b
>>>>>>> REPLACE
```

The local tool requires a unique, exact complete-line match, including indentation, with no fuzzy matching. It plans all edits before making changes and rejects empty, missing, ambiguous, unauthorized or ineffective edits. The tool renders a standard Git diff from those exact edits; it does not use reference answers, fix model-written diffs, or guess the intended old code. The same source/reference/test controls are then applied inside fresh isolated containers.

Mechanical checks converted the 20 private reference repairs into exact edits and restored the exact clean source bytes for every task. No downloaded source was executed on the host. Fifteen implementation tests passed, including authored correct, incorrect and missing-search executable cases. **These checks do not constitute 20 successful model repairs.** GPU generation and model evaluation for this new format have now completed; final outcomes are recorded in Section 18.

### Files for Ankita

Notebook:
`C:\repositories\self-verifying-ai-app-generator-clean\training\notebooks\SVAGA_Dev20_SearchReplace_Base_vs_Adapter.ipynb`

New prompt ZIP:
`C:\repositories\self-verifying-ai-app-generator-clean\data\evaluation\repair-dev20-search-replace-v1\repair-dev20-search-replace-prompts.zip`

Upload that ZIP and the same `C:\Users\ankit\Downloads\SVAGA_Qwen15B_10K_Final.zip` when the new notebook requests two files. Use a fresh Colab T4 runtime. No 10K dataset upload or training is needed. Prompts range from 546 to 3,534 tokens with the pinned tokenizer.

New persistent output:

```text
/content/drive/MyDrive/SVAGA/repair-dev20-search-replace-qwen15b-v1/search_replace_generation_results.json
```

Download the completed 40-output JSON. The local one-task preflight command is:

```powershell
cd "C:\repositories\self-verifying-ai-app-generator-clean"
python -B training/run_search_replace_eval.py --predictions "C:\Users\ankit\Downloads\search_replace_generation_results.json" --limit 1 --output "results/repair_eval/search-replace-preflight"
```

After preflight, run the full frozen comparison with `--limit 20` and a new output directory. For an interrupted run, repeat its exact command with `--resume` and the same output directory; source and input hashes must match. Add `--pull-missing` only when official images are absent and their downloads are intended. Private reference/task metadata stays local.

The existing adapter was trained on unified diffs, not SEARCH/REPLACE blocks. This pilot measures prompting/format compatibility with existing weights; it does not demonstrate the quality of a separately fine-tuned SEARCH/REPLACE model. If it improves application and test outcomes, a future training-format change must be a separately versioned experiment. Four-model training and Terminal-Bench evaluation remain separate outstanding work.

Background: [Aider's edit-format documentation](https://aider.chat/docs/more/edit-formats.html) describes SEARCH/REPLACE as one editing representation. Our pilot uses the stricter exact-line/unique-match policy described above, without Aider's possible recovery heuristics.


## 18. SEARCH/REPLACE results — 26 October 2026

All 40 new outputs were downloaded, checked against the separately frozen prompt packet and adapter hashes, and executed through the same clean/buggy/reference-restored test controls. All 20 task pairs had valid reference environments. Logged prompt lengths match the full frozen inputs: no input truncation was detected.

| Format / weights | Applied edits | Fully passing repairs |
|---|---:|---:|
| Unified diff / base | 0/20 | 0/20 |
| Unified diff / trained adapter | 3/20 | 0/20 |
| Exact SEARCH/REPLACE / base | 1/20 | 0/20 |
| Exact SEARCH/REPLACE / trained adapter | 1/20 | 0/20 |

The base's one applied SEARCH/REPLACE edit fixed **4 of 7 observed failing tests**, but left three failures; all 21 regression controls stayed passing. The adapter's one applied edit fixed **0 of 6 observed failing tests** and preserved all 119 regression controls. Partial test improvements are useful diagnostics but are not complete task success.

Final SEARCH/REPLACE failure counts:

- Base: six exact searches not found; 13 unsupported file paths; one applied edit failed tests.
- Adapter: three exact searches not found; 15 unsupported file paths; one malformed edit response; one applied edit failed tests.
- Neither variant reached the output-token limit in this format.

### Prompt-example-copying limitation

Five base outputs and 11 adapter outputs mention the illustrative `src/example.py` from the format example. That file is not a permitted target in any selected task. Other outputs invented paths such as a `src/` prefix rather than using the supplied file path. Those edits were rejected, not redirected or repaired automatically.

This is an important limitation of the prompt trial: the concrete example became a distraction for some generations. The result measures this exact prompt with these existing weights, not the general usefulness of SEARCH/REPLACE. The existing adapter was fine-tuned for unified-diff targets. No new-format training was done, and no outputs were regenerated after failures.

### Artifacts

Verified downloaded generation copy:
`C:\repositories\self-verifying-ai-app-generator-clean\results\repair_eval_inputs\repair-dev20-search-replace-v1\search_replace_generation_results.json`

Generation SHA256:
`ff44939b508d428b84c77c30ca8f65dcfe4d7ac260445804833b9d88f6350769`

Final result folder:
`C:\repositories\self-verifying-ai-app-generator-clean\results\repair_eval\search-replace-full-20261026`

It contains `summary.json`, all 40 `reports.json` records, `verification.json`, per-attempt logs/XML, source snapshots, `format_comparison.csv`, and the task-by-task `paired_format_comparison.csv`.

There are **20 unique executable development tasks** here, reused across two formats and two weight conditions: 80 generated outputs in total, not 80 independent tasks. This is separate from the 1,000-example prediction-loss evaluation and from planned Terminal-Bench/Harbor evaluation.

### Recommended next step

The format switch alone did not produce a fully working repair, although one base edit partially fixed a task. Keep both experiments as honest baselines. Avoid treating the 28.28% lower loss as a functional-success gain.

Next, agree on an actual larger model from Kapil's candidate list and an available GPU. Check tokenizer lengths, model loading, a real-data backward/update step, checkpoint reload, and executable generation in a small preflight. Measure the larger model's unfine-tuned baseline on the frozen tasks before comparing its trained adapter. Use the original frozen diff condition for a like-for-like baseline, or clearly name any new prompt/format condition. Do not overwrite the existing 10K dataset, baseline results or artifacts, and do not assume the current T4 can fit every lab candidate.

The four specialist model/approach implementations and the independent Terminal-Bench evaluation remain outstanding. This completed experiment is a diagnostic result, not a claim of production readiness.


## 19. Larger-model preparation — 26 October 2026

Ankita chose **her Colab account, with the available GPU checked first**. No larger model has been loaded or trained. Qwen3-Coder-30B-A3B-Instruct is a provisional candidate from Kapil's recorded list, conditional on hardware and a real-data preflight.

The cached pinned tokenizer was checked against all frozen records: 10,000 training records (maximum 4,073 tokens) and 1,000 development-validation records (maximum 4,075), all fitting 4,096 without truncation. Both original data hashes matched. This changes neither the training package nor its verification status.

Immediate user action: open `training/notebooks/SVAGA_Larger_Model_Hardware_Check.ipynb` in Colab, connect a GPU and run its single hardware-only cell. Share the printed report before model downloads. The notebook was syntax-checked and its probe executed locally; that local Windows check is not a Colab/GPU training test.

Full next-step plan: `training/LARGER_MODEL_PREFLIGHT.md`. Audit: `data/audits/larger-model-preflight-20261026/qwen3-coder-30b-token-lengths.json`. The first prospective loading/backward/save/reload experiment and larger-model executable baseline remain pending hardware confirmation. The current 1.5B adapter must not be loaded onto the candidate model.


A100 update (26 October): Ankita reported NVIDIA A100-SXM4-40GB, 39.08 GiB free VRAM, 81.83 GiB available host RAM, CUDA-enabled PyTorch 2.11.0+cu130. Hardware screen passed. Unsloth and bitsandbytes are not yet installed; software compatibility and real-data memory/save/reload preflight remain pending. Larger-model weights have not been loaded or fine-tuned. User-supplied hardware report: `data/audits/larger-model-preflight-20261026/colab-a100-user-report.json`.


30B loading update (26 October): Ankita reported Qwen3-Coder-30B-A3B-Instruct loaded in 4-bit at the exact pinned revision on the A100, with 15.56 GiB allocated and 16.85 GiB peak during loading. No adapter attached and no training performed. Next is the frozen dataset/runtime tokenization-and-masking check, then a disposable-adapter real-data backward/save/reload preflight. The larger-model executable baseline and full 10K training have not started.


30B data update: Ankita confirmed exact ZIP/record hashes, the native loaded chat-template fingerprint, all 11,000 tokenized records and assistant boundaries. No model forward pass or optimizer update has occurred yet. A two-example train-only disposable adapter test is prepared in `training/colab_qwen3coder30b_train_preflight.py`; its actual execution and adapter restoration remain pending.


30B training preflight update: Ankita completed two disposable train-only LoRA updates, including the longest 4,073-token input, with finite loss/gradients and 16.95 GiB peak allocated VRAM. Both initial and updated pilot adapters were saved to Drive. This is not full 10K training. Fresh-base restoration testing is prepared in `training/colab_qwen3coder30b_reload_preflight.py` and remains pending actual Colab execution. No larger-model validation or executable repair results have been collected yet.


30B reload check FAILED (26 October): exact adapter tensor and tokenizer checks passed, but the two loss comparisons exceeded the original tolerance; no success marker was created and the full 10K run remains pending. We found an inconsistency in the check (LoRA requires_grad True before reload, all False after) and prepared an evaluation-only diagnostic. The cause is not established; preserve the failed results and do not loosen the tolerance to declare success.


30B reload diagnostic update: all repeated evaluations were exactly stable and unaffected by LoRA trainable/frozen flags. Thus the requires_grad inconsistency does not explain the original mismatch in the observed diagnostic. The original failure is preserved. A new one-update disposable controlled reproduction with complete serialized frozen-base/quantization fingerprints is prepared; its execution and the full 10K run remain pending.


30B controlled persistence PASS: all 1,491 serialized frozen-base tensors/quantization metadata matched exactly before and after a disposable update and after fresh reload; saved adapter tensors matched and both loss differences were 0.0. Original failed report remains preserved and unexplained. No full 10K run has started. Next prepared cell restores the original zero-update adapter and measures a 100-record base development-loss baseline, followed by frozen executable development base generation and then a separately checkpointed full run.


30B baseline completed: original zero-update adapter restored; disabled-adapter loss on the fixed 100-record development subset was 0.6843285933464144. Full training remains unstarted. A model-specific prompt-only packet and generation cell are prepared for the same 20 executable development tasks; model context is 8,192 to accommodate the longest 3,366-token prompt plus 2,048 output tokens without shortening inputs or budgets. Raw base generations must be saved before fine-tuning.


30B pre-training generations completed: all 20 base outputs were downloaded and locally provenance-verified, 6,832 output tokens, zero cap hits. Executable scores remain pending. Actual full-run training code is prepared with a first segment of 10 updates / 80 records, followed by continuation through update 1,250, durable hashed Drive checkpoints and recovery checks. Full 10K training has not started in the evidence received so far.


Session recovery: Ankita reinstalled the pinned dependencies after the initial training attempt failed at import. A one-cell restore is prepared for Drive artifacts, the correct initial/complete-checkpoint adapter and frozen dataset, without repeating pilots or base generations. No new training execution has been reported yet. Checkpoint presence and successful restoration remain pending the user-run recovery cell.


30B actual training COMPLETE: the user log reached update 1,250 / 10,000 examples and saved final checkpoint step-01250. Post-training evaluation/export is prepared; results have not yet been reported. Use the 8K-runtime dev100 baseline 0.6829081848793719 for its immediate comparison. No functional or external-benchmark success is implied by the training log.


30B dev100 result: 0.6829081848793719 → 0.22452987680875175, a 67.12% relative prediction-loss reduction. Final adapter/tokenizer export saved to Drive. This does not establish functional repair accuracy. A full fresh-base final-adapter/tokenizer reload check with frozen-state fingerprints and 100 per-task loss comparisons is prepared and pending execution.


Final 30B export verification: adapter tensors, tokenizer inputs and all serialized frozen-base tensors matched exactly, but strict dev100 loss reproduction failed (25/100 per-task matches; aggregate difference 0.00015397). Keep these distinct findings; do not report numerical verification as passed or repeat training to chase the tolerance. A short normal/uncompiled diagnostic and explicitly labeled evidence backup are prepared. Cause, full dev1000 and functional scores remain pending.


30B backup downloaded and verified locally: all original/export evidence hashes matched; extracted artifacts are in `results/fine_tuning/qwen3coder30b-context-10k-v1`. Compiler mode changes selected losses reproducibly but does not restore the original golden values, so strict numerical reproducibility remains open. The next prepared cell generates only 20 trained answers and pairs them with the untouched 20 pre-training answers for executable evaluation.
