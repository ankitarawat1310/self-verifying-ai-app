# Run in the SAME Colab session after successful 30B loading.
from google.colab import files
from pathlib import Path
import hashlib
import io
import json
import statistics
import time
import zipfile

assert globals().get("model") is not None, "Load the pinned 30B model first."
assert MODEL_ID == "Qwen/Qwen3-Coder-30B-A3B-Instruct"
assert getattr(model.config, "_commit_hash", None) == REVISION
assert not getattr(model, "peft_config", None), "Run this before attaching a preflight adapter."
assert RUN_ROOT.exists()

uploaded = files.upload()  # Select only swesmith-context-repair-10k-v2.zip.
assert len(uploaded) == 1, "Select only the frozen 10K dataset ZIP."
zip_name, zip_bytes = next(iter(uploaded.items()))
sha = lambda data: hashlib.sha256(data).hexdigest()
assert sha(zip_bytes) == "b55b143fc41ec5dd35e1aca897168a293b83e6d83ecc698973d79318519fe3fd", "Wrong or changed dataset ZIP."
expected = {
    "train.jsonl": "36d790d8f87c19cf2d914863cb8a3be7c1be3c2e74d5af183fd3755b0a802eec",
    "validation.jsonl": "3953a213500952e1b03f003514d36b2b5c6c661ed5a387cbc278d7d588fd02dc",
}
with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
    assert len(archive.namelist()) == 3 and set(archive.namelist()) == {"manifest.json", *expected}
    manifest = json.loads(archive.read("manifest.json"))
    rows = {}
    for split, count in (("train", 10000), ("validation", 1000)):
        raw = archive.read(split + ".jsonl")
        assert sha(raw) == expected[split + ".jsonl"] == manifest["files_sha256"][split + ".jsonl"]
        rows[split] = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
        assert len(rows[split]) == count
        assert len({r["instance_id"] for r in rows[split]}) == count
for key in ("instance_id", "repo", "bug_patch_sha256", "buggy_excerpts_sha256"):
    assert not {r[key] for r in rows["train"]} & {r[key] for r in rows["validation"]}, "Split overlap: " + key
print("Verified original 10,000 training + 1,000 development-validation records.")

# The manifest's stored token lengths were measured for the OLD 1.5B tokenizer.
# Recalculate with the actual loaded 30B tokenizer; do not reuse those lengths.
tokenizer = getattr(tokenizer, "tokenizer", tokenizer)
template_sha = sha(json.dumps(tokenizer.chat_template, sort_keys=True).encode())
print("Loaded chat-template SHA256:", template_sha)
assert template_sha == "83c830fd6a2f75e8927d915f6b033af6e84c98199231530e065adc05fe3f67b5", "Loaded chat template differs from the pinned native tokenizer audit. Stop and review."

def token_ids(messages, generation_prompt):
    ids = tokenizer.apply_chat_template(messages, tokenize=True,
        add_generation_prompt=generation_prompt, truncation=False, return_dict=False)
    assert isinstance(ids, list) and ids and all(isinstance(v, int) for v in ids)
    return ids

prepared = {}
data_report = {"scope": "30B_runtime_data_and_masking_preparation_only",
    "model": MODEL_ID, "revision": REVISION,
    "source_zip_sha256": sha(zip_bytes), "input_sha256": expected,
    "chat_template_sha256": template_sha,
    "source_manifest_tokenizer": manifest["tokenizer"],
    "tokenizer_library": software["transformers"],
    "splits": {}, "training_performed": False,
    "data_status": manifest["status"],
    "notes": ["Same frozen records and targets; native 30B token lengths recomputed.",
              "Prompt positions will be masked with -100; only assistant targets are supervised.",
              "Development validation is separate and must never enter optimizer steps.",
              "This verifies formatting and masking, not correctness of the repair targets."]}
for split in ("train", "validation"):
    examples, details = [], []
    for row in rows[split]:
        messages = row["messages"]
        assert [m["role"] for m in messages] == ["user", "assistant"]
        full = token_ids(messages, False)
        prompt = token_ids(messages[:1], True)
        assert 0 < len(prompt) < len(full) <= 4096, row["instance_id"]
        assert full[:len(prompt)] == prompt, "Assistant boundary mismatch: " + row["instance_id"]
        labels = [-100] * len(prompt) + full[len(prompt):]
        assert all(v == -100 for v in labels[:len(prompt)])
        assert labels[len(prompt):] == full[len(prompt):]
        example = {"task": row["instance_id"], "input_ids": full,
                   "prompt_length": len(prompt), "target_tokens": len(full) - len(prompt)}
        examples.append(example)
        details.append({"task": example["task"], "total_tokens": len(full),
                        "prompt_tokens": len(prompt), "target_tokens": example["target_tokens"]})
        if len(examples) % 1000 == 0:
            print(split + ": " + str(len(examples)) + " prepared", flush=True)
    prepared[split] = examples
    lengths = [len(e["input_ids"]) for e in examples]
    data_report["splits"][split] = {"records": len(examples), "shortest": min(lengths),
        "median": statistics.median(lengths), "longest": max(lengths),
        "target_tokens": sum(e["target_tokens"] for e in examples), "rows": details}
    print(split.upper(), "records:", len(examples), "longest:", max(lengths),
          "target tokens:", data_report["splits"][split]["target_tokens"])

# Fixed train-only selection: one SHA-ordered example plus the longest example.
first = min(prepared["train"], key=lambda e: sha(e["task"].encode()))
longest = max(prepared["train"], key=lambda e: (len(e["input_ids"]), e["task"]))
preflight_examples = list({e["task"]: e for e in (first, longest)}.values())
data_report["selected_train_only_preflight_tasks"] = [e["task"] for e in preflight_examples]
for example in preflight_examples:
    print("PREFLIGHT TRAIN", example["task"], "total:", len(example["input_ids"]),
          "target:", example["target_tokens"])

destination = RUN_ROOT / ("data-check-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + ".json")
with destination.open("x") as stream:
    json.dump(data_report, stream, indent=2)
print("Saved:", destination)
print("Prepared only. No forward pass, adapter attachment, optimizer update or truncation.")
