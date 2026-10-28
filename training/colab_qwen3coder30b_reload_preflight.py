# SAME A100 Colab session, immediately after the TWO-UPDATE disposable pilot.
# Evaluates persistence only. It does not perform optimizer updates.
import gc
import hashlib
import json
import math
from pathlib import Path
import time
import torch
from unsloth import FastModel
from peft import get_peft_model_state_dict, set_peft_model_state_dict
from safetensors.torch import load_file

assert globals().get("model") is not None
assert globals().get("PREFLIGHT_ROOT") is not None
assert (PREFLIGHT_ROOT / "TRAINING_COMPLETE").exists()
assert not (PREFLIGHT_ROOT / "reload-check.json").exists(), "Reload report already exists; do not rerun."
assert not (PREFLIGHT_ROOT / "reload-reference.json").exists(), "Reload already started. Stop and review the saved reference before retrying."
assert getattr(model.config, "_commit_hash", None) == REVISION
saved_report = json.loads((PREFLIGHT_ROOT / "report.json").read_text())
assert saved_report["status"] == "two_updates_completed_reload_not_yet_checked"
assert len(saved_report["updates"]) == 2
assert [e["task"] for e in preflight_examples] == [e["task"] for e in saved_report["examples"]]
for relative, expected_sha in saved_report["files_sha256"].items():
    path = PREFLIGHT_ROOT / relative
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha, "Saved file changed: " + relative

adapter_dir = PREFLIGHT_ROOT / "trained_adapter"
config = json.loads((adapter_dir / "adapter_config.json").read_text())
assert config["base_model_name_or_path"] == MODEL_ID
assert config["revision"] == REVISION
assert config["peft_type"] == "LORA"
assert config["r"] == 16 and config["lora_alpha"] == 16
assert config["lora_dropout"] == 0 and config["bias"] == "none"
assert set(config["target_modules"]) == {"q_proj", "k_proj", "v_proj", "o_proj"}
assert not config.get("modules_to_save") and not config.get("use_dora") and not config.get("use_rslora")
assert not config.get("rank_pattern") and not config.get("alpha_pattern")
assert not config.get("target_parameters")

saved_adapter = load_file(str(adapter_dir / "adapter_model.safetensors"), device="cpu")
assert saved_adapter and all("lora_" in key for key in saved_adapter)

def compare_adapter_weights(current_model, expected):
    current = get_peft_model_state_dict(current_model)
    assert set(current) == set(expected), "Adapter key mismatch."
    for key, tensor in current.items():
        actual = tensor.detach().cpu()
        assert actual.shape == expected[key].shape and actual.dtype == expected[key].dtype, key
        assert torch.equal(actual, expected[key]), "Adapter tensor differs: " + key
    return True

assert compare_adapter_weights(model, saved_adapter)

def reload_losses(current_model, examples):
    current_model.eval()
    current_model.config.use_cache = False
    details = []
    with torch.no_grad():
        for example in examples:
            ids = torch.tensor([example["input_ids"]], dtype=torch.long, device="cuda")
            labels = ids.clone()
            labels[:, :example["prompt_length"]] = -100
            count = int((labels[:, 1:] != -100).sum().item())
            assert count == example["target_tokens"] > 0
            with torch.autocast("cuda", dtype=torch.bfloat16):
                output = current_model(input_ids=ids, attention_mask=torch.ones_like(ids), labels=labels, use_cache=False)
            value = float(output.loss.float())
            assert math.isfinite(value)
            details.append({"task": example["task"], "loss": value, "target_tokens": count})
            print("Reload check evaluation:", example["task"], "loss:", value, flush=True)
            del ids, labels, output
    return details

print("Evaluating the current saved pilot adapter before releasing the model...", flush=True)
before_reload = reload_losses(model, preflight_examples)
reference = {"model": MODEL_ID, "revision": REVISION, "software": saved_report["software"],
    "scope": "saved_adapter_reload_reference_no_optimizer_updates", "before": before_reload,
    "adapter_files_sha256": saved_report["files_sha256"],
    "examples": preflight_examples}
with (PREFLIGHT_ROOT / "reload-reference.json").open("x") as stream:
    json.dump(reference, stream, indent=2)

# Release the old base before loading a fresh base. Keep CPU examples/reference only.
for name in ("trainable", "trainable_named", "model"):
    globals().pop(name, None)
torch.compiler.reset()  # Clear compiled-graph caches before reclaiming old model storage.
gc.collect()
torch.cuda.empty_cache()
print("GPU allocated after releasing old model (GiB):", round(torch.cuda.memory_allocated() / 2**30, 3), flush=True)
assert torch.cuda.memory_allocated() / 2**30 < 4, "Old GPU model storage is still referenced. Stop and share this output; do not load a second base."

print("Reloading the exact base checkpoint from the existing local cache...", flush=True)
started = time.perf_counter()
model, reload_tokenizer = FastModel.from_pretrained(
    model_name=MODEL_ID, revision=REVISION, use_exact_model_name=True,
    max_seq_length=4096, dtype=torch.bfloat16, load_in_4bit=True,
    full_finetuning=False, device_map={"": 0}, trust_remote_code=False,
    local_files_only=True,
)
assert getattr(model.config, "_commit_hash", None) == REVISION
assert getattr(model, "is_loaded_in_4bit", False)
model = FastModel.get_peft_model(
    model, r=config["r"], lora_alpha=config["lora_alpha"], lora_dropout=config["lora_dropout"],
    bias=config["bias"], target_modules=sorted(config["target_modules"]),
    use_gradient_checkpointing="unsloth", random_state=42,
)
model.peft_config["default"].revision = REVISION
outcome = set_peft_model_state_dict(model, saved_adapter, adapter_name="default")
assert not outcome.unexpected_keys, outcome.unexpected_keys
assert not any("lora_" in key for key in outcome.missing_keys), "Missing adapter weights."
assert compare_adapter_weights(model, saved_adapter)
model.requires_grad_(False)
model.eval()
model.config.use_cache = False

# Confirm this newly loaded tokenizer produces the same IDs and assistant boundary.
reload_tokenizer = getattr(reload_tokenizer, "tokenizer", reload_tokenizer)
assert hashlib.sha256(json.dumps(reload_tokenizer.chat_template, sort_keys=True).encode()).hexdigest() == data_report["chat_template_sha256"]
source_rows = {row["instance_id"]: row for row in rows["train"] if row["instance_id"] in {e["task"] for e in preflight_examples}}
for example in preflight_examples:
    messages = source_rows[example["task"]]["messages"]
    full_ids = reload_tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False, truncation=False, return_dict=False)
    prefix_ids = reload_tokenizer.apply_chat_template(messages[:1], tokenize=True, add_generation_prompt=True, truncation=False, return_dict=False)
    assert full_ids == example["input_ids"] and len(prefix_ids) == example["prompt_length"]
    assert full_ids[:len(prefix_ids)] == prefix_ids

after_reload = reload_losses(model, preflight_examples)
comparisons = []
for before, after in zip(before_reload, after_reload):
    assert before["task"] == after["task"]
    diff = abs(after["loss"] - before["loss"])
    match = math.isclose(before["loss"], after["loss"], rel_tol=1e-4, abs_tol=1e-5)
    comparisons.append({"task": before["task"], "saved_model_loss": before["loss"],
                        "reloaded_model_loss": after["loss"], "absolute_difference": diff, "match": match})
reload_report = {
    "scope": "fresh_base_plus_saved_disposable_adapter_reload_no_optimizer_updates",
    "model": MODEL_ID, "revision": REVISION, "fresh_base_loaded": True,
    "saved_adapter_tensors_match_exactly": True, "tokenizer_inputs_match": True,
    "comparisons": comparisons, "loss_comparison_tolerance": {"rtol": 1e-4, "atol": 1e-5},
    "match": all(item["match"] for item in comparisons),
    "reload_and_evaluation_seconds": time.perf_counter() - started,
    "optimizer_updates_in_this_check": 0, "full_training_started": False,
    "limitations": ["These are persistence-check losses on the two pilot training examples, not validation results or repair scores.",
        "The loaded adapter still contains two disposable pilot updates. Do not start the full run from it.",
        "Full training must restore the separately saved initial adapter, create a new optimizer and reset RNG/run state."]}
with (PREFLIGHT_ROOT / "reload-check.json").open("x") as stream:
    json.dump(reload_report, stream, indent=2)
print(json.dumps(reload_report, indent=2))
assert reload_report["match"], "Loss comparison failed. Stop and inspect the saved report."
(PREFLIGHT_ROOT / "RELOAD_MATCH").write_text("Fresh pinned base and saved adapter restored; no optimizer updates in reload check.\n")
tokenizer = reload_tokenizer
print("Fresh-base saved-adapter reload: MATCH. Full 10K training has not started.")
