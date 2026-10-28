# Pilot tokenizer check: action required before training

Measured all 100 pilot training and 20 pilot validation conversations using each
candidate's default chat template, with no truncation. No model weights were loaded.
Dataset files and splits were not changed. This is not a full 11,000-record audit.

| Model | Previously successful dummy-run length | Training records fitting | Validation records fitting |
|---|---:|---:|---:|
| Qwen3-Coder-30B-A3B-Instruct | 24,576 tokens | 79/100 | 15/20 |
| Qwen3.6-27B | 16,384 tokens | 45/100 | 8/20 |
| GPT-OSS-20B, Unsloth 4-bit | 8,192 tokens | 3/100 | 1/20 |
| Devstral-Small-2-24B-Instruct-2512 | No successful lab training length established | Not applicable | Not applicable |

Devstral tokenization succeeded; its training failure is a separate issue.
At an illustrative 8,192-token cap, 2/100 Devstral training records and 0/20
validation records fit. This does NOT demonstrate trainability at that cap.

Maximum observed training-example lengths: Qwen Coder 41,286; Qwen3.6 31,143;
GPT-OSS 40,535; Devstral 43,036 tokens. These are formatted conversation lengths,
not assistant-only supervised token counts. Model templates may treat reasoning
text differently. Final template options and loss masks must be checked explicitly.

## Interpretation for Kapil

Do not start full training with silent truncation to 8K: nearly all pilot records
would be cut, potentially removing fixes or verification steps. Earlier dummy-run
limits are observed hardware/software results, NOT the model's advertised maximum
context and NOT guarantees that real-data training will fit.

Next, agree on a processing strategy: sufficient longer-context hardware, or a
carefully validated turn-based/windowed representation preserving required context
and target answers. Any derived windows must retain source task IDs and their
original split; report source-record and training-window counts separately.
Do not merely cut a long conversation every N tokens or move windows between splits.
Keep the frozen original 10K/1K package unchanged. No such conversion is done yet.

## Reproducibility

Script: training/check_model_token_lengths.py.
Successful report: data/audits/tokenizer-pilot-four-models-v2.json.
The earlier tokenizer-pilot-four-models.json contains a failed attempt caused by
missing Jinja2 and must not be used for length statistics.

Report includes exact model/tokenizer revision hashes, template hashes and input
file hashes. CPU-only environment: Transformers 5.20.2, tokenizers 0.23.3,
SentencePiece 0.2.2, Jinja2 3.1.6. Devstral uses fix_mistral_regex=True.
PyTorch is intentionally absent from this separate .venv-tokenizer environment.
Kapil should reproduce counts with his pinned training environment before use.
