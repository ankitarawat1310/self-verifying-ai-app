# Larger-model preflight: Ankita's Colab

Updated 26 October 2026. Ankita reported an A100-SXM4-40GB Colab runtime (39.08 GiB free VRAM, 81.83 GiB available RAM). Hardware screening passed; no larger model has been loaded or trained.

## Immediate action

1. Open `training/notebooks/SVAGA_Larger_Model_Hardware_Check.ipynb` in personal Colab: File > Upload notebook.
2. Select a GPU runtime and connect. Run the single code cell.
3. Share its printed report. Do not run the old 1.5B training cells for this new experiment.

The cell reports GPU, free/total VRAM, RAM, disk and software. It installs nothing and downloads no weights. The 22 GiB memory screen is a project policy based on Kapil's recorded RTX 4090 experiment, not an official minimum or a guarantee. A T4 fails this screen for the proposed 30B setup. An L4/4090 passing it still requires a real-data fit check; a larger GPU is not automatically available on a paid Colab plan.

## Provisional candidate and evidence

`Qwen/Qwen3-Coder-30B-A3B-Instruct`, pinned tokenizer revision `b2cff646eb4bb1d68355c01b18ae02e7cf42d120`, is from Kapil's actual list. This is a proposed next model, not a substitute claim that four models have been fine-tuned.

Kapil's `training/lab_reference/bench_Qwen_Qwen3-Coder-30B-A3B-Instruct.json` records 20.5 decimal GB peak allocated GPU memory at 16,384 tokens, with Unsloth, synthetic repeated code, rank-16 attention adapters and an RTX 4090. Its after-load allocation was 16.8 decimal GB. Those numbers are environment-specific; they are not the RAM/VRAM needed for our complete real-data run and do not predict Colab runtime.

## Completed CPU tokenizer audit

Frozen package: `data/prepared/swesmith-context-repair-10k-v2`. Both input SHA256 hashes match the completed 1.5B experiment.

| Split | Records | Median tokens | Maximum | Fit within 4,096 |
|---|---:|---:|---:|---:|
| Training | 10,000 | 1,414 | 4,073 | 10,000 |
| Development validation | 1,000 | 1,272.5 | 4,075 | 1,000 |

Measured with the candidate's pinned native chat template, without truncation. No weights loaded. No rows, targets or splits changed. Token fit does not establish memory fit or repair correctness. The data still represents experimental localized-repair imitation with supplied affected locations; it is not verified secure-application training data.

Report: `data/audits/larger-model-preflight-20261026/qwen3-coder-30b-token-lengths.json` (includes every task's token count).

Reproduction, from the repository root, choosing a new report filename:

```powershell
.\.venv-tokenizer\Scripts\python.exe -B training/larger_model_preflight.py audit --data-dir data/prepared/swesmith-context-repair-10k-v2 --output data/audits/qwen3-coder-token-lengths-new.json
```

The audit uses cached tokenizer files only and fails on modified dataset hashes. The hardware probe can also run as `python training/larger_model_preflight.py hardware --output hardware-new.json` on the intended GPU machine.

## Steps after hardware confirmation

1. Select and record the actual model revision, quantized weight source, software versions and compatible Unsloth loading recipe for that GPU. A third-party prequantized weight source is a distinct artifact and must be recorded; it is not implicitly identical to dynamically quantizing the official checkpoint.
2. Run one real-data forward/backward/update and adapter save/reload check, including a longest example. Use a disposable preflight adapter and separate output folder; do not use its updated weights as the unfine-tuned baseline. Check assistant-only masking under the new tokenizer, finite loss/gradients, peak memory and timings. Avoid treating a single successful step as proof that the full run is stable.
3. Generate the unfine-tuned larger model's outputs on the same fixed 20 development tasks using the original unified-diff instruction and recorded greedy output budget. Make a new model-specific manifest and token audit; the old manifest pins the 1.5B model and cannot be reused unchanged. Reuse the established isolated executable controls. Keep outputs unchanged.
4. If the preflight is stable, start a fresh adapter for a separately named full 10K run, with resumable persistent checkpoints and a recorded experiment configuration. Preserve the current data/splits, 1.5B weights, results and notebook.
5. Evaluate base versus trained adapter on the same development loss and executable tasks. Record application rate, resolved tasks, regressions and limitations, even when loss decreases.

Never attach the 1.5B adapter to this larger model. Do not copy its results as larger-model results. The small development set has already been examined; external Terminal-Bench/Harbor evaluation and the four specialist approaches remain separate work.

## Official references

- [Qwen model card](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct): model identity, architecture and native use.
- [Unsloth Qwen3-Coder documentation](https://unsloth.ai/docs/models/tutorials/qwen3-coder-how-to-run-locally): supported execution/fine-tuning ecosystem; inference quantization examples do not establish training fit.
- [Colab FAQ](https://research.google.com/colaboratory/faq.html): available GPU types and resource limits vary over time, including paid plans.


## Hardware confirmed: A100 Colab

Ankita supplied the hardware-only report dated 2026-10-26T18:06:22Z. The report is recorded at `data/audits/larger-model-preflight-20261026/colab-a100-user-report.json`; this is user-supplied Colab evidence, not a local GPU measurement.

Next install and verify compatible training dependencies in this separate larger-model runtime. Preserve the working CUDA PyTorch build during dependency resolution. A resolver conflict is a reason to inspect compatibility, not to remove all constraints or install with `--no-deps`. Record the resolved versions and restart the session before importing Unsloth ahead of Transformers/PEFT. This does not start training. Do not use Run all on the earlier 1.5B notebook.


## Dependency verification completed

Ankita reported a successful 4-bit linear GPU calculation after restart: Unsloth/Zoo 2026.10.9, Transformers 5.17.0, CUDA PyTorch 2.11.0+cu130, PEFT 0.21.2, Accelerate 1.15.0, bitsandbytes 0.50.2. Unsloth reports a PyTorch attention fallback because xformers was built for a different PyTorch/CUDA combination. Keep this fallback recorded; model loading and real-data training are not yet proven. Note that Transformers changed from the earlier tokenizer-audit version 5.20.2 to 5.17.0; recheck tokenization/masking in the actual runtime before training.

Next Colab loading cell is saved at `training/colab_qwen3coder30b_load_preflight.py`. It pins the official model revision, requests exact model identity rather than an automatic mirror, records software/load reports to a separate Drive preflight folder, and attaches no adapter. The code was syntax-checked locally, but the 30B loading operation has not been executed locally. The official unquantized checkpoint download is substantially larger than a prequantized mirror; this is an intentional source choice and may take time. If the installed loader rejects an option or revision check, stop and inspect the error rather than silently dropping provenance constraints.


## Official pinned 30B model loaded in Colab

Ankita reported successful exact-revision 4-bit loading on the A100: 351.7 seconds, 15.56 GiB allocated after load, 16.85 GiB peak, no adapter and no training. Recorded at `data/audits/larger-model-preflight-20261026/colab-load-user-report.json`. This establishes loading only, not backward-pass capacity.

Next cell: `training/colab_qwen3coder30b_data_preflight.py`. Upload only the existing `data/prepared/swesmith-context-repair-10k-v2.zip`. The cell checks the exact ZIP and JSONL hashes, counts and split isolation; checks the loaded native chat-template fingerprint; recomputes all 30B token lengths and verifies the assistant boundary for masked loss. It selects two deterministic training-only examples including the longest for a future disposable-adapter test. It performs no forward pass or optimizer update. Its syntax and local ZIP identity were checked; the actual Colab tokenizer check remains pending.


## Loaded-tokenizer data check passed

Ankita reported all 10,000 training and 1,000 validation records prepared with the native pinned template matching the audit. Maximum lengths were 4,073 / 4,075 and assistant targets 3,389,665 / 332,113. Split/hash/masking checks passed, without truncation or training. Two deterministic training-only examples are 1,684 and 4,073 tokens. Evidence: `data/audits/larger-model-preflight-20261026/colab-data-user-report.json`.

Next cell: `training/colab_qwen3coder30b_train_preflight.py`. This performs exactly two disposable real-data optimizer updates, checks finite loss and nonzero finite gradients, restricts trainable parameters to LoRA attention adapters, records memory/timing, saves initial and trained adapters separately to Drive, and explicitly leaves persistence/reload validation pending. It matches the lab attention target family/rank (r=16 q/k/v/o), uses bf16 and masked prompt loss, and tests the longest training example. The code was syntax-checked locally; no 30B training was run locally. Two successes would not establish a 10K success or a repair score. Do not rerun after partial failure or reuse the pilot-updated adapter as the start of the full experiment.


## Two disposable real-data updates completed

Ankita reported two successful updates, including the longest 4,073-token example: 13,369,344 trainable attention-LoRA parameters, 16.95 GiB peak allocated / 17.65 GiB peak reserved memory. Losses 0.542161 and 0.186420 are on different training examples, so they are not a before/after improvement comparison. The 50.2-second first step and 6.7-second second step do not establish average full-run throughput. The trained and initial pilot adapters were saved separately in Drive at `qwen3coder30b-preflight-v1/disposable-3f354f1b83b1`.

Next script: `training/colab_qwen3coder30b_reload_preflight.py`. It checks all previously recorded artifact hashes, verifies saved adapter tensors match the live pilot, records pre-release losses on both pilot examples, releases the old base, reloads the exact official base from cache, creates the recorded LoRA architecture, restores its saved tensors with PEFT, checks exact tensor equality and tokenizer IDs, and compares the same two losses with explicit numeric tolerance. It performs zero optimizer updates. It refuses to load a second base if old model GPU storage remains. The script is syntax-checked, not GPU-tested locally. The reloaded trained pilot remains disposable and must not seed the full 10K run; restore initial state and use a new optimizer for that run.


## Reload loss comparison FAILED; full run remains pending

Ankita supplied the saved reload report: adapter tensors and tokenizer inputs matched exactly, but losses differed by 0.00462842 and 0.00055936, failing the predeclared rtol=1e-4 / atol=1e-5. `RELOAD_MATCH` does not exist. Preserve `reload-check.json` and `reload-reference.json`; do not relax tolerance or mark the check passed. Evidence: `data/audits/larger-model-preflight-20261026/colab-reload-failed-user-report.json`.

Code review found an evaluation-path confound in our check: pre-release adapter parameters were trainable, whereas all parameters were frozen for the post-reload losses. This is an implementation inconsistency, not proof of the mismatch cause. New cell `training/colab_qwen3coder30b_reload_diagnostic.py` runs evaluation-only consecutive passes in frozen, LoRA-trainable-flags and frozen-again states on the current model, checks RNG consumption, module training flags and unchanged saved adapter tensors, and records comparisons using the original tolerance. It restores original flags and preserves failed reports. It performs no optimizer updates, model reload or new training. Syntax was checked locally; actual diagnostic outcome remains pending Colab execution. Stable repeats alone would not establish identical quantized base weights across fresh loads.


## Repeated-pass diagnostic: requires_grad hypothesis not supported

Ankita supplied the evaluation-only diagnostic. All 12 forward losses were identical within each task across frozen / LoRA-trainable-flags / frozen-again settings and consecutive repetitions: 0.5111947059631348 and 0.1787520945072174. No module remained in training mode, no CPU/CUDA RNG state was consumed, and adapter tensors were unchanged. These observations do not support the requires_grad-setting explanation for the original mismatch. The earlier failed reload remains failed.

Next prepared controlled reproduction: `training/colab_qwen3coder30b_controlled_reload.py`. It adds ONE explicitly disposable update to the already disposable pilot, fingerprints every serialized non-LoRA base tensor (including serialized bitsandbytes quantization state) before/after update and after a cached exact-base reload, keeps evaluation settings identical and compares saved adapters and repeated losses. Hashes stream in small CPU chunks rather than copying the full base into RAM. It stops before reload if frozen serialized state changes during the update/mode transition, and records detailed changed-key identities if the reload changes state. It preserves all original reports; any success applies only to this new controlled experiment. Syntax-checked locally, not GPU-tested. Actual outcome pending Colab. No full 10K training has started.


## Controlled reproduction passed exactly

Ankita supplied the controlled follow-up: all 1,491 serialized non-LoRA base tensors and serialized quantization metadata had the same SHA256 before update, after update and after fresh reload: `8fd14ef2fc10a40bf6c6ca4057626212b0f20e57b3e536ea1e05e14176720063`. The saved adapter tensors matched, repeated evaluation was stable and both reload loss differences were exactly zero (0.5155941843986511 / 0.18819601833820343 before and after). This new control passed; it does not retroactively explain or erase the original failure. Evidence: `data/audits/larger-model-preflight-20261026/colab-controlled-reload-user-report.json`.

The physical loading, data preparation, bounded training and controlled persistence checks are now demonstrated in the reported A100 runtime. Full 10K training remains unstarted. Next cell `training/colab_qwen3coder30b_baseline.py` verifies and restores the separately saved initial adapter (all LoRA B matrices zero), checks that no pilot updates carry over, creates a new full-experiment folder, and evaluates the disabled-adapter base model on the same deterministic SHA-ordered 100 development task IDs used in the earlier 1.5B subset. Native tokenization and runtime differences are recorded; cross-model loss is not an architecture-only ablation. No optimizer is created in the baseline cell. Frozen dev20 base generation is a separate pending step before full training.


## Base development-loss baseline completed

Ankita restored the original untrained adapter exactly and reported disabled-adapter base token-weighted loss **0.6843285933464144** on the fixed SHA-ordered 100 development records. No optimizer updates or full training occurred. The new full-experiment folder is `/content/drive/MyDrive/SVAGA/context-qwen3coder30b-10k-v1`. The score is prediction loss, not repair accuracy.

Next: `training/colab_qwen3coder30b_dev20_base.py` and `data/evaluation/repair-dev20-qwen3coder30b-base-v1/repair-dev20-qwen3coder30b-base-prompts.zip`. The prompt and private task bytes match the original 20-task unified-diff condition exactly; only the public manifest is model-specific. The upload ZIP contains only manifest/prompts. Native prompt lengths are 378–3,366; adding the unchanged 2,048 output allowance needs 5,414 tokens, so the script reloads the exact cached base with 8,192 model context and restores the zero-update adapter. Training inputs still cap at 4,096. It records a neutral repetition penalty of 1.0 and the complete effective generation configuration; earlier model-specific inherited generation settings were not fully pinned, limiting an architecture-only cross-model interpretation. It generates 20 base outputs with the adapter disabled, saves each unchanged and supports same-metadata partial-run continuation. No generated commands execute and no training occurs. Local packet identities/token lengths and code syntax were checked; actual 30B generations remain pending.


## All 20 base generations completed and downloaded

Ankita completed the 8,192-context base condition. The downloaded JSON was found and independently checked locally: 20 records, 6,832 output tokens, no generation-limit hits, 1,059.62 recorded generation seconds. Every prompt hash/length and model/revision/decoding field matched the frozen packet. Raw file SHA256: `c18170d7dc6c1b1be567c7b48ea3b19677fdb25c5b0462aec2a8250feaee7c28`. Preserved at `results/repair_eval_inputs/repair-dev20-qwen3coder30b-base-v1/qwen3coder30b_dev20_base_generations.json`. Warnings about deprecated mixed generation kwargs and inherited max_length were retained; all outputs completed under the 2,048-token cap. No repairs have been executed for this 30B condition yet.

Next actual-training cell: `training/colab_qwen3coder30b_train_10k.py`. It checks generation completion, verifies the zero-update initial adapter, restores training/gradient-checkpointing mode after inference, records a separate pre-training baseline under the actual 8K runtime (preserving the earlier 4K loss), and starts the real 10K one-epoch run. It pauses after 10 updates / 80 records for a measured ETA; those records remain part of the same epoch. Continue with `train_30b_segment(1250)`. The effective batch is eight, giving 1,250 optimizer updates. Checkpoints save adapter, tokenizer, optimizer, shuffled order, progress and RNG states, with file hashes and COMPLETE markers at step 0, step 1, every 50 and segment/final ends. All complete checkpoints are retained (several GB of Drive storage for the full run). A failed/interrupted partial update requires restoring an owned complete checkpoint. Runtime code is syntax-checked but actual GPU execution remains pending.


## Session recovery required before full training

The first full-training-cell attempt stopped at `from unsloth import FastModel` with ModuleNotFoundError, before any update in that attempt. Ankita then reported the A100 still present but Unsloth/bitsandbytes absent, Transformers reset to 5.20.2, no model/prepared data, and Drive inaccessible. This indicates missing session state; unmounted Drive is not evidence of lost persistent artifacts. Complete checkpoints remain unknown until mounted. Recovery installation cell: `training/colab_qwen3coder30b_recover_install.py`, pinned to the reported successful versions (including Transformers 5.17.0 and Unsloth/Zoo 2026.10.9) while preserving CUDA PyTorch. After restart, inspect Drive/checkpoints, restore the correct owned adapter and frozen dataset, and continue the existing experiment. Do not repeat pilot tests or regenerate pre-training answers.


## One-cell session recovery prepared

After Ankita reinstalled the pinned dependencies and reported completion/restart, `training/colab_qwen3coder30b_recover_session.py` was prepared. It imports Unsloth first, verifies the exact software/A100 screen, mounts Drive, verifies the saved baseline/20-generation SHA256, and selects the highest COMPLETE-marked owned training checkpoint if one exists. Checkpoint file hashes/configuration/progress must verify; corruption stops recovery rather than silently falling back. If none exists, it verifies the saved original zero-update adapter against its original artifact. It then accepts only the same frozen 10K ZIP, restores the exact base and correct adapter at 8K context, and prepares all 11K examples with native assistant boundaries without training or repeated evaluation. The model may need downloading again in the new VM. Complete checkpoint presence is not yet known until Colab execution.

The actual training cell now reads `RECOVERY_CHECKPOINT_30B` from this verified recovery result automatically; its algorithm/config fingerprint fields were not changed. Resume optimizer/RNG state is still verified and loaded by the actual training runtime, not unpickled by the recovery cell. Recovery code is syntax-checked locally; actual runtime restoration remains pending.


## FULL 10K epoch completed — user log confirmed

Ankita reported the full one-epoch Qwen3-Coder-30B-A3B run completed: 10,000 training records / 1,250 optimizer updates, final `step-01250` saved, 16.96 GiB peak allocated VRAM. The last logged group training loss was 0.1613; it is not validation loss. The canonical pre-training 100-record development loss in the actual 8K runtime was **0.6829081848793719**; preserve the earlier 4K-context value 0.6843285933464144 separately.

Next cell: `training/colab_qwen3coder30b_evaluate_export.py`. It verifies final checkpoint hashes and exact equality with the live trained adapter, evaluates the same 100 development records and target-token counts, and creates a new `final_export` by copying/hash-checking final checkpoint adapter/tokenizer artifacts. It does not copy the full base weights or optimizer state into the export. Fresh final-adapter reload, full 1,000-record comparison, trained dev20 generation/executable comparison and external Terminal-Bench evaluation remain pending. This code was syntax-checked locally; actual post-training GPU evaluation is pending.


## Trained dev100 evaluation/export completed

Ankita reported matching final checkpoint/live adapter integrity and completed the same 100-record evaluation: before **0.6829081848793719**, after **0.22452987680875175**, relative prediction-loss reduction **67.12151328975324%**. The adapter/tokenizer and reports were exported to Drive `final_export`, with no extra optimizer updates. This is not executed-repair accuracy.

Next cell: `training/colab_qwen3coder30b_final_reload.py`. It checks the immutable export hashes, exact live/exported adapter equality, fingerprints all serialized frozen-base/quantization tensors, frees the previous model/optimizer storage, reloads the pinned base at 8K context from cache, reconstructs the recorded attention-LoRA architecture and restores exported tensors, reloads the exported tokenizer and verifies the 100 native input/mask boundaries, evaluates the same 100 rows and compares aggregate AND per-task losses at the original declared tolerance. Frozen-base hashes must also match. Reports are supplemental in `final_verification`; the original export/evaluation remains preserved. An already saved final-reload report is displayed instead of running the expensive check again. Code was syntax-checked locally; actual fresh final-adapter restoration remains pending Colab execution.


## Final exported artifacts match; strict dev100 numerical reproduction FAILED

Ankita reported exact adapter tensors, exact tokenizer inputs and identical complete serialized frozen-base fingerprints (`8fd14ef2...720063`, all 1,491 tensors), but the strict loss check failed: saved 0.22452987680875175 vs reloaded 0.2243759044354284, aggregate difference 0.00015397237332334668; only 25/100 per-task comparisons passed and maximum difference was 0.008091390132904053. Preserve the failure and original tolerance. Artifact identity and numerical reproduction are separate results. Do not retrain the completed model merely to make this check pass, and do not assert the cause has been established.

Next bounded cell: `training/colab_qwen3coder30b_numeric_diagnostic_backup.py`. It evaluates the three largest disagreements and one matching control in normal vs force-eager compiler modes, twice each (at most 16 forwards), on the current loaded model. No model reload/optimizer/training. This is a diagnostic selection, not a performance sample; disabling torch.compile does not disable every custom Unsloth kernel. It checks unchanged adapter tensors and preserves the original failed report, then downloads a versioned evidence ZIP containing original exported bytes plus current verification/status. The backup explicitly records artifact restoration identity PASS and strict numerical loss reproduction FAIL. Full dev1000 paired loss and executable repairs remain pending. Syntax-checked locally; actual diagnostic/backup pending Colab execution.

Primary API reference: [PyTorch 2.11 set_stance](https://docs.pytorch.org/docs/2.11/generated/torch.compiler.set_stance.html). [PyTorch numerical accuracy](https://docs.pytorch.org/docs/2.11/notes/numerical_accuracy.html) explains that mathematically equivalent execution paths need not produce bitwise-identical floating-point results; it does not by itself diagnose this run.


## Compiler diagnostic and downloaded evidence verified

Ankita downloaded `SVAGA_Qwen3Coder30B_10K_Training_Evidence_v1.zip` (51,915,530 bytes), SHA256 `be1cdf5e82dd33620ebbd449ad1318258871208bbb474b3162da60a04cc17c49`. Local verification checked every original-export and evidence-manifest hash, and safely extracted 22 files to `results/fine_tuning/qwen3coder30b-context-10k-v1`. Final adapter SHA256: `5c908232cef5cd63bb30e135c1435c6ecfefc78e868740b46bce744fffaea20c`. The strict loss failure remains explicitly recorded.

Normal and force-eager diagnostic modes each produced exactly stable repeats but different per-case values; force-eager did not recover the original pre-reload values on the discrepant examples. This demonstrates compiler/execution-path sensitivity in the selected diagnostic cases, not a conclusive diagnosis or passing reproduction test. No further training or model reload occurred.

Next: `training/colab_qwen3coder30b_dev20_trained.py` with `data/evaluation/repair-dev20-qwen3coder30b-paired-v1/repair-dev20-qwen3coder30b-paired-prompts.zip`. The paired manifest freezes the actual exported full-run adapter/tokenizer hashes. Same prompt/private task bytes and source base outputs are preserved. Only 20 trained outputs are generated in the already loaded model, with the original greedy/budget/software settings; they are saved alongside the 20 untouched pre-training outputs and cross-linked to the original file/manifest SHA256. No training, new model load or generated-command execution. Executable comparison and full dev1000 remain pending.


## Completed 30B paired executable development evaluation — 26 October 2026

The downloaded paired generation JSON (SHA256 `30c8fc44883bad97baea0f3acc16bc702c31fcd632b95368a0117fea1cdaba92`) contains the 20 unchanged original base records plus 20 trained-adapter records. All model/prompt/adapter/decoding identities verified; no token-cap hits. Full execution completed in fresh network-disabled official containers, with no host mounts and no candidate rewriting/fuzzy matching. The existing reviewed native path / preinstalled packaging-metadata compatibility was applied equally to both conditions; clean, buggy and restored reference controls remain required.

Final results: base **1/20 passing**, adapter **4/20 passing**. Base 16/20 format-accepted and 3/20 applied; adapter 20/20 format-accepted and 6/20 applied. Two applied patches in each condition failed tests. No observed pass-to-pass regressions among executed candidates. Adapter wins four tasks, base wins one, neither passes 15. All 20 pairs have valid reference controls; 19 reproduce every listed upstream failure. The first Trio task has three already-passing upstream labels (18/21 failures reproduced), recorded explicitly without changing the required generated-repair test set.

Evidence audit passed on all 40 records and 129 stage XML/outcome pairs, checking exact generated patch bytes and recomputed summaries. Results: `results/repair_eval/qwen3coder30b-paired-20261026`. These are small development results with supplied affected locations, not Terminal-Bench or security certification. Existing strict fresh-reload numerical failure remains unchanged.

Next prepared cell: `training/colab_qwen3coder30b_full_dev1000.py`. It evaluates base and trained adapter in the same loaded model on all 1,000 development rows, masks prompts from loss, verifies saved adapter/input/runtime identities and saves per-condition progress with same-instance guards. It performs no training or model reload. It is locally syntax-checked; actual Colab full-development results remain pending. The earlier 100-record loss result and failed numerical reproducibility report remain preserved as separate evidence.


## Full dev1000 completed and final 30B handover — 26 October 2026

The downloaded `full_dev1000_same_instance_comparison.json` contains 1,000 unique development tasks for each condition, with the same order, 332,113 target tokens and zero optimizer updates. Local auditing checked software/model/adapter identities, task order and target counts against the frozen dataset, zero training/validation task overlap, finite losses and recomputed token-weighted summaries. Independent CPU tokenization using the exported native tokenizer regenerated the exact prepared-validation SHA256 `db4278afffaf9827a0037e32b30df4ba215c3e22339da1b587b649df13d2f11e`. No model weights loaded for the CPU check.

Full-development base loss **0.6508693447994254**; adapter **0.20910277191314444**; relative reduction **67.87331073679889%**. Raw report SHA256: `5711253e20a172fe865291f2d3434559cd79ffa39a91c8f9c08fcd99cae5f6ee`. Preserved with verification in `results/fine_tuning/qwen3coder30b-full-dev1000-20261026`. These are reported Colab GPU forwards with local evidence verification, not GPU evaluations repeated locally.

The strict numerical reload failure remains preserved. Final handover: `training/KAPIL_30B_FINAL_HANDOVER_2026-10-26.md`; machine status: `training/handover-qwen3coder30b-2026-10-26.json`. This completes the current 30B training/evaluation handover, not the external benchmark or four-model project.
