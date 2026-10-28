# Kapil handover: completed Qwen 1.5B and 30B fine-tuning runs

**From:** Ankita Rawat  
**Date:** 26 October 2026  
**Project:** `C:\repositories\self-verifying-ai-app-generator-clean`  
**Status:** Two Qwen fine-tuning runs are complete: Qwen2.5-Coder-1.5B-Instruct and Qwen3-Coder-30B-A3B-Instruct. Each used the same frozen 10,000-example training set and has full dev1000 loss evaluation plus a 20-task executable repair comparison. The broader four-model project and external benchmark are still pending.

## Completed models at a glance

We completed **4-bit LoRA fine-tuning of both models**, not just pilot tests. Each trained for one epoch on the same frozen 10,000 examples (1,250 optimizer updates), with 1,000 additional development-validation examples.

| Model | Full dev1000 loss: base to fine-tuned | Relative loss reduction | Fully passing repairs: base to fine-tuned |
|---|---:|---:|---:|
| Qwen/Qwen2.5-Coder-1.5B-Instruct | 0.4616815888 to 0.3311282826 | 28.28% | 0/20 to 0/20 |
| Qwen/Qwen3-Coder-30B-A3B-Instruct | 0.6508693448 to 0.2091027719 | 67.87% | 1/20 to 4/20 |

**Earlier 1.5B run:** revision `2e1fd397ee46e1388853d2af2c993145b0f1098a`; Colab Tesla T4; LoRA rank 8 targeting q_proj/v_proj. The saved-adapter reload loss comparison matched exactly in that workflow. Three trained-adapter patches applied on the frozen unified-diff development sample, but none passed all required tests; one introduced regression failures. These results are separate from the later search/replace experiment.

**30B run:** LoRA rank 16 targeting q_proj/k_proj/v_proj/o_proj on an A100; detailed results and its unresolved strict numerical reload issue are documented below.

The 1.5B model is a **supporting small-model baseline**. Count it among the required four models only if the team explicitly includes it in the agreed model list. The two runs differ in precision, runtime, LoRA configuration and some generation settings; this is not a controlled ablation isolating model size. Lower prediction loss is not proof of a working or secure application.

1.5B evidence: `results/fine_tuning/qwen15b-context-10k-v2` (adapter, tokenizer, full-development report and reload check); `results/repair_eval/repair-dev20-native-path-compat-20261026/summary.json` (final unified-diff summary); `training/handover-evidence-2026-10-25.json` (earlier machine-readable handover). The updated share ZIP includes the exact 1.5B export ZIP plus these summary/evaluation records, alongside the complete 30B evidence.

## 1. Detailed 30B run

We fine-tuned **Qwen/Qwen3-Coder-30B-A3B-Instruct**, revision `b2cff646eb4bb1d68355c01b18ae02e7cf42d120`, using 4-bit LoRA on a Colab A100-SXM4-40GB.

The model reads an issue and supplied buggy Python context, then predicts a repair as a unified diff. We trained small adapter matrices while keeping the base model weights frozen. This is fine-tuning of the 30B model, not training all its weights from scratch. The trained adapter must be loaded with the matching pinned base model.

- Training: **10,000 examples**, one epoch, **1,250 optimizer updates**.
- Full development validation: **1,000 examples**, additional to training, evaluated with the adapter disabled and enabled in one loaded model instance.
- Executable development evaluation: **20 frozen tasks**, 40 generated repairs across the two conditions, tested in isolated official Docker environments.
- Adapter, tokenizer, training configuration, loss reports and failure evidence are saved and downloaded. Original evidence is preserved.

## 2. Final results to report

| Metric | Base model | Fine-tuned adapter |
|---|---:|---:|
| Full dev1000 token-weighted prediction loss | 0.6508693448 | 0.2091027719 |
| Fully passing executable repairs | 1/20 (5%) | 4/20 (20%) |
| Format-accepted generated diffs | 16/20 | 20/20 |
| Patches successfully applied | 3/20 | 6/20 |
| Applied repairs that failed tests | 2/20 | 2/20 |

The full-development prediction loss fell **67.87%**. Loss measures how well the model predicts recorded repair tokens when given the correct preceding tokens. It is not a success percentage or application-security score. Each condition covers the same 1,000 task IDs and **332,113 supervised target tokens**; prompt tokens are excluded from the loss.

The executable repair rate increased **15 percentage points**, from 5% to 20%. Four tasks passed only with the adapter; one passed only with the base; 15 passed with neither. Thus improvement is not universal. Four base outputs had invalid format. Fourteen adapter patches and 13 base patches did not apply. No pass-to-pass regression failures were observed among the applied candidates, but this does not establish security or complete correctness.

All 20 task pairs passed clean, buggy and restored reference controls. One Trio task reproduces 18 of 21 upstream fail-to-pass labels; three already pass in the buggy environment. All named tests are still required for a passing repair. The other 19 tasks reproduce all listed failures. The local evidence audit checked 40 reports and 129 stage/JUnit XML pairs without modifying generated output or rerunning tests.

The earlier dev100 loss result (0.6829081849 to 0.2245298768, 67.12%) is a separate historical measurement. Use the full dev1000 numbers above for the completed full-development result; do not mix the two protocols or denominators.

## 3. Dataset to use

**Frozen package:** `data/prepared/swesmith-context-repair-10k-v2.zip`  
**Expanded folder:** `data/prepared/swesmith-context-repair-10k-v2`  
**Source:** official `SWE-bench/SWE-smith-py`, revision `77cab9055d42ab4a5c25c89a8f937096db13558e`.

- `train.jsonl`: 10,000 distinct tasks from 119 repository identities.
- `validation.jsonl`: 1,000 distinct tasks from 12 separate repository identities.
- No exact task/repository overlap across the prepared splits. The local final audit rechecked zero training/validation task overlap.
- Inputs contain issue text, known affected locations, buggy functions and selected supporting context. Targets reverse the official bug-introducing patch.
- Native 30B tokenization: longest training record 4,073 tokens; validation 4,075. All fit the 4,096 training-example cap; no truncation was used.
- Package status remains `experimental_training_package_not_verified_repair_corpus`. Bulk reference targets have not all been independently executed.

This is localized Python repair data, not complete secure-application generation data and not Terminal-Bench. Supplied affected locations simplify repository localization. The development set has been inspected repeatedly and is not an untouched final test set. The dataset manifest retains its original 1.5B tokenizer metadata; the 30B native preparation was separately recorded and verified.

```text
Dataset ZIP SHA256:
b55b143fc41ec5dd35e1aca897168a293b83e6d83ecc698973d79318519fe3fd
train.jsonl SHA256:
36d790d8f87c19cf2d914863cb8a3be7c1be3c2e74d5af183fd3755b0a802eec
validation.jsonl SHA256:
3953a213500952e1b03f003514d36b2b5c6c661ed5a387cbc278d7d588fd02dc
```

## 4. Training configuration and environment

| Setting | Recorded value |
|---|---|
| Hardware | Colab NVIDIA A100-SXM4-40GB |
| Quantization / computation | 4-bit base / bfloat16 compute |
| LoRA | rank 16, alpha 16, dropout 0, bias none |
| LoRA targets | q_proj, k_proj, v_proj, o_proj |
| Trainable parameters | 13,369,344 (reported 0.0438%) |
| Batch | microbatch 1; accumulate 8 examples |
| Optimizer | AdamW; learning rate 0.00002; weight decay 0; gradient clip 1 |
| Training | one shuffled epoch; seed 42; 1,250 updates |
| Context | 8,192 model context; individual training examples capped at 4,096 |
| Supervision | assistant repair tokens only; prompt labels masked |
| Peak allocated training VRAM | 16.96 GiB in this recorded configuration |

Software: Python 3.13.16; PyTorch 2.11.0+cu130; Transformers 5.17.0; PEFT 0.21.2; Accelerate 1.15.0; bitsandbytes 0.50.2; Unsloth and Unsloth Zoo 2026.10.9. xformers was incompatible with this PyTorch build, so PyTorch attention fallback was used. Preserve these versions for reproduction; the measured memory usage is not a guarantee for another configuration.

## 5. Important unresolved result

**Saved artifact identity passed; strict numerical reload reproduction failed.**

The exported adapter tensors, tokenizer inputs and all 1,491 serialized frozen-base/quantization tensors matched exactly after fresh reload. However, dev100 loss changed from 0.2245298768 to 0.2243759044, exceeding the original strict tolerance. Only 25/100 per-task comparisons matched. The cause is not conclusively established; compiler/execution-path diagnostics showed sensitivity but did not resolve it.

The failure and original tolerance are preserved. The new full-dev1000 result compares both conditions in the same loaded instance and does not erase or resolve the cross-reload failure. No retraining is required merely to make the current handover complete.

## 6. Where the artifacts are

All local paths below are relative to the project root named at the top.

| Artifact | Location |
|---|---|
| Verified exported adapter/tokenizer and original evidence | `results/fine_tuning/qwen3coder30b-context-10k-v1` |
| Adapter weights | `results/fine_tuning/qwen3coder30b-context-10k-v1/adapter/adapter_model.safetensors` |
| Final full-development JSON and local audit | `results/fine_tuning/qwen3coder30b-full-dev1000-20261026` |
| Executable summary, comparison, reports, logs and XML | `results/repair_eval/qwen3coder30b-paired-20261026` |
| Frozen paired evaluation packet | `data/evaluation/repair-dev20-qwen3coder30b-paired-v1` |
| Machine-readable final handover status | `training/handover-qwen3coder30b-2026-10-26.json` |
| Earlier small-model/experiment history | `training/KAPIL_HANDOVER_2026-10-25.md` |

Drive experiment root: `/content/drive/MyDrive/SVAGA/context-qwen3coder30b-10k-v1`.

- Final complete training checkpoint: `step-01250`.
- Exported adapter/tokenizer: `final_export`.
- Full-development report: `full-dev1000-same-instance-v1/full_dev1000_same_instance_comparison.json`.
- Paired generated outputs: `dev20-paired/qwen3coder30b_dev20_paired_generations.json`.
- Optimizer/RNG/progress recovery checkpoints remain on Ankita's Drive. They are not included in the downloaded model-evidence ZIP.

The share bundle `handover/SVAGA_Kapil_Qwen3Coder30B_2026-10-26_v2.zip` includes this document, the exact frozen dataset ZIP, the exact downloaded training-evidence ZIP, the complete local full-development/repair evaluation evidence, the paired packet and relevant script snapshots. It is an evidence handover, not a full project checkout or a runnable container image. Full base-model weights are not included; use the exact pinned upstream base. No account credentials are needed or included.

Inside the original downloaded evidence, `STATUS.json` and some README fields say evaluation was pending at export time. They are historical and kept unchanged. This final document, the supplementary completion JSON and the later evaluation folders provide the current status.

## 7. Kapil's next steps

1. Extract the share ZIP and verify its files against `BUNDLE_MANIFEST.json`; read this document first. Retain the original downloaded training-evidence ZIP and the dataset ZIP.
2. Use the existing project checkout and the exact pinned base plus exported adapter/tokenizer for inference. Do not treat the adapter as a complete standalone model or merge it into a differently quantized/revised base without a separate check.
3. Review the remaining repair failures, especially corrupt/non-applying diff hunks. Preserve raw outputs and fixed budgets when comparing changes. Any output-repair/postprocessing experiment must be reported separately from these frozen results.
4. Complete external Terminal-Bench/Harbor evaluation with a frozen task inventory, independent environment validation and a suitable agent interface. That benchmark has not yet run; a localized diff predictor needs an explicit integration plan for broader terminal tasks.
5. Plan and preflight the remaining required fine-tuned models. The earlier 1.5B run is a supporting baseline; it is not automatically one of the four selected models in Kapil's plan. Four base models and the four SVAGA approaches are separate requirements; the current dataset trains repair behavior, not all four specialist approaches.
6. Preserve the numerical reload issue as open. Keep software, quantization, kernels, model revision, adapter hashes, tokenization and compiler policy attached to every future comparison.

**Ready-to-share summary:** We completed 4-bit LoRA fine-tuning of Qwen2.5-Coder-1.5B and Qwen3-Coder-30B on the same 10K SWE-smith repair examples. The 1.5B supporting baseline reduced full-development prediction loss by 28.28%, with 0/20 fully passing repairs before and after fine-tuning. On all 1K development examples, loss fell 67.87%; on 20 executable development tasks, passing repairs increased from 1 to 4. Artifacts and evidence are saved. Most repairs still fail, strict numerical reload reproduction remains unresolved, and external benchmarking plus the remaining models are next.
