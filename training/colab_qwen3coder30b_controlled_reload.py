# SAME A100 Colab session after the stable repeated-pass diagnostic.
# One additional DISPOSABLE update, then a fingerprinted cached reload.
# Original failed reports and adapters are never overwritten.
import gc, hashlib, json, math, time, uuid
from pathlib import Path
import torch
from unsloth import FastModel
from peft import get_peft_model_state_dict, set_peft_model_state_dict
from safetensors.torch import load_file

SOURCE_ROOT = Path("/content/drive/MyDrive/SVAGA/qwen3coder30b-preflight-v1/disposable-3f354f1b83b1")
assert globals().get("model") is not None
assert getattr(model.config, "_commit_hash", None) == REVISION
assert json.loads((SOURCE_ROOT / "reload-check.json").read_text())["match"] is False
assert not (SOURCE_ROOT / "RELOAD_MATCH").exists()
assert not globals().get("controlled_reload_started", False), "Controlled test already started. Stop and review its report before rerunning."
reference = json.loads((SOURCE_ROOT / "reload-reference.json").read_text())
control_examples = reference["examples"]
assert len(control_examples) == 2
assert [len(e["input_ids"]) for e in control_examples] == [1684, 4073]
source_config = json.loads((SOURCE_ROOT / "trained_adapter/adapter_config.json").read_text())
assert source_config["r"] == 16 and source_config["bias"] == "none"
assert set(source_config["target_modules"]) == {"q_proj", "k_proj", "v_proj", "o_proj"}
control_source_adapter = load_file(str(SOURCE_ROOT / "trained_adapter/adapter_model.safetensors"), device="cpu")
control_live = get_peft_model_state_dict(model)
assert set(control_live) == set(control_source_adapter)
assert all(torch.equal(t.detach().cpu(), control_source_adapter[k]) for k, t in control_live.items())
del control_live
CONTROL_ROOT = SOURCE_ROOT / ("controlled-reload-" + uuid.uuid4().hex[:12])
CONTROL_ROOT.mkdir(exist_ok=False)
controlled_reload_started = True
control_report = {"scope":"one_additional_disposable_update_and_fingerprinted_reload", "model":MODEL_ID,
    "revision":REVISION, "source_pilot":str(SOURCE_ROOT), "software":software,
    "original_reload_check_passed":False, "full_training_started":False, "additional_optimizer_updates":0,
    "original_failed_report_sha256":hashlib.sha256((SOURCE_ROOT / "reload-check.json").read_bytes()).hexdigest(),
    "limitations":["This is a new controlled reproduction; it does not erase or explain the original failure by itself.",
        "Frozen-state hashes cover serialized non-LoRA tensors, including serialized quantization metadata; nonserialized implementation caches are outside that hash.",
        "These are pilot training examples, not evaluation scores. Do not use the updated pilot to start full training."]}

def save_control():
    (CONTROL_ROOT / "report.json").write_text(json.dumps(control_report, indent=2))


def frozen_fingerprint(current_model, label):
    # Stream every serialized non-adapter tensor in bounded chunks; no full CPU model copy.
    details, total = {}, 0
    state = current_model.state_dict()
    names = sorted(name for name in state if "lora_" not in name)
    print("Fingerprinting frozen base:", label, "tensors:", len(names), flush=True)
    for number, name in enumerate(names, 1):
        value = state[name].detach()
        assert isinstance(value, torch.Tensor), name
        flat = value.reshape(-1)
        digest = hashlib.sha256()
        # Limit each temporary CPU chunk to approximately 16 MiB.
        chunk_elements = max(1, (16 * 2**20) // max(1, value.element_size()))
        for start in range(0, flat.numel(), chunk_elements):
            array = flat[start:start+chunk_elements].contiguous().view(torch.uint8).cpu().numpy()
            digest.update(memoryview(array))
        details[name] = {"dtype":str(value.dtype), "shape":list(value.shape), "sha256":digest.hexdigest()}
        total += value.numel() * value.element_size()
        if number % 1000 == 0:
            print(label, number, "/", len(names), "tensors hashed", flush=True)
    root_sha = hashlib.sha256(json.dumps(details, sort_keys=True).encode()).hexdigest()
    result = {"state_sha256":root_sha, "serialized_bytes":total, "tensors":details}
    (CONTROL_ROOT / (label + "-base-fingerprint.json")).write_text(json.dumps(result, indent=2))
    print(label, "base fingerprint:", root_sha, flush=True)
    return result


def eval_control(current_model):
    current_model.requires_grad_(False)
    current_model.eval()
    current_model.config.use_cache = False
    assert not any(module.training for module in current_model.modules())
    values = []
    with torch.no_grad():
        for example in control_examples:
            ids = torch.tensor([example["input_ids"]], dtype=torch.long, device="cuda")
            labels = ids.clone(); labels[:,:example["prompt_length"]] = -100
            assert int((labels[:,1:] != -100).sum()) == example["target_tokens"]
            with torch.autocast("cuda", dtype=torch.bfloat16):
                output = current_model(input_ids=ids, attention_mask=torch.ones_like(ids), labels=labels, use_cache=False)
            loss = float(output.loss.float()); assert math.isfinite(loss)
            values.append({"task":example["task"], "loss":loss})
            del ids, labels, output
    return values


def single_control_update(current_model):
    current_model.requires_grad_(False)
    for name, parameter in current_model.named_parameters():
        if "lora_" in name:
            parameter.requires_grad_(True)
    parameters = [p for p in current_model.parameters() if p.requires_grad]
    assert sum(p.numel() for p in parameters) == 13369344
    optimizer = torch.optim.AdamW(parameters, lr=2e-5, weight_decay=0)
    current_model.train(); current_model.config.use_cache = False
    example = control_examples[0]  # Same fixed training-only 1,684-token example.
    print("Starting ONE additional disposable update:", example["task"], flush=True)
    started = time.perf_counter()
    try:
        optimizer.zero_grad(set_to_none=True)
        ids = torch.tensor([example["input_ids"]], dtype=torch.long, device="cuda")
        labels = ids.clone(); labels[:,:example["prompt_length"]] = -100
        with torch.autocast("cuda", dtype=torch.bfloat16):
            output = current_model(input_ids=ids, attention_mask=torch.ones_like(ids), labels=labels, use_cache=False)
            loss = output.loss
        assert torch.isfinite(loss).item()
        loss.backward()
        norm = torch.nn.utils.clip_grad_norm_(parameters, 1., error_if_nonfinite=True)
        assert math.isfinite(float(norm)) and float(norm) > 0
        assert all(p.grad is None for p in current_model.parameters() if not p.requires_grad)
        optimizer.step(); torch.cuda.synchronize()
        assert all(torch.isfinite(p).all().item() for p in parameters)
        return {"task":example["task"], "loss":float(loss.detach().float()),
                "gradient_norm":float(norm), "seconds":time.perf_counter()-started}
    finally:
        optimizer.zero_grad(set_to_none=True)
        current_model.requires_grad_(False); current_model.eval()

save_control()
# Warm the same frozen evaluation path before taking the first complete fingerprint.
control_report["pre_update_losses"] = eval_control(model)
control_base_before = frozen_fingerprint(model, "before-update")
control_report["update"] = single_control_update(model)
control_report["additional_optimizer_updates"] = 1
control_report["pre_reload_pass1"] = eval_control(model)
control_report["pre_reload_pass2"] = eval_control(model)
control_base_after = frozen_fingerprint(model, "after-update")
changed_during_update = [name for name in set(control_base_before["tensors"]) | set(control_base_after["tensors"])
    if control_base_before["tensors"].get(name) != control_base_after["tensors"].get(name)]
control_report["frozen_base_unchanged_during_update_and_mode_transition"] = not changed_during_update
control_report["changed_base_keys_during_update"] = changed_during_update
model.peft_config["default"].revision = REVISION
model.save_pretrained(CONTROL_ROOT / "trained_adapter", safe_serialization=True)
control_weights_path = CONTROL_ROOT / "trained_adapter/adapter_model.safetensors"
control_saved = load_file(str(control_weights_path), device="cpu")
control_report["control_adapter_sha256"] = hashlib.sha256(control_weights_path.read_bytes()).hexdigest()
control_report["status"] = "one_update_saved_before_reload"
save_control()
if changed_during_update:
    control_report["status"] = "stopped_base_serialized_state_changed_during_update"
    save_control()
    print(json.dumps({k:v for k,v in control_report.items() if k != "limitations"}, indent=2))
    raise RuntimeError("Frozen serialized base state changed. Preserve this report and share it; no reload or full training started.")
assert all(math.isclose(a["loss"], b["loss"], rel_tol=1e-4, abs_tol=1e-5)
           for a,b in zip(control_report["pre_reload_pass1"], control_report["pre_reload_pass2"])), "Unstable pre-reload evaluation; stop."

# Drop all known global live-tensor aliases before reloading; fingerprints contain hashes only.
for name in ("model", "trainable", "trainable_named", "control_live"):
    globals().pop(name, None)
torch.compiler.reset(); gc.collect(); torch.cuda.empty_cache()
allocated = torch.cuda.memory_allocated() / 2**30
print("Allocated after releasing model (GiB):", allocated, flush=True)
assert allocated < 4, "Old model memory remains referenced. Stop before loading a second base."
model, control_tokenizer = FastModel.from_pretrained(
    model_name=MODEL_ID, revision=REVISION, use_exact_model_name=True,
    max_seq_length=4096, dtype=torch.bfloat16, load_in_4bit=True,
    full_finetuning=False, device_map={"":0}, trust_remote_code=False, local_files_only=True)
assert getattr(model.config, "_commit_hash", None) == REVISION
model = FastModel.get_peft_model(model, r=16, lora_alpha=16, lora_dropout=0, bias="none",
    target_modules=["q_proj","k_proj","v_proj","o_proj"],
    use_gradient_checkpointing="unsloth", random_state=42)
model.peft_config["default"].revision = REVISION
outcome = set_peft_model_state_dict(model, control_saved, adapter_name="default")
assert not outcome.unexpected_keys and not any("lora_" in k for k in outcome.missing_keys)
assert set(get_peft_model_state_dict(model)) == set(control_saved)
assert all(torch.equal(t.detach().cpu(), control_saved[k]) for k,t in get_peft_model_state_dict(model).items())
control_report["adapter_tensors_match_after_reload"] = True
control_report["post_reload_pass1"] = eval_control(model)
control_report["post_reload_pass2"] = eval_control(model)
control_base_reloaded = frozen_fingerprint(model, "reloaded")
changed_on_reload = [name for name in set(control_base_after["tensors"]) | set(control_base_reloaded["tensors"])
    if control_base_after["tensors"].get(name) != control_base_reloaded["tensors"].get(name)]
control_report["frozen_base_serialized_state_matches_across_reload"] = not changed_on_reload
control_report["changed_base_keys_on_reload"] = changed_on_reload
control_report["changed_base_key_details_first_10"] = [{"name":name,
    "before":control_base_after["tensors"].get(name), "after":control_base_reloaded["tensors"].get(name)} for name in changed_on_reload[:10]]
control_report["comparisons"] = [{"task":a["task"],"before":a["loss"],"after":b["loss"],
    "absolute_difference":abs(a["loss"]-b["loss"]),
    "match":math.isclose(a["loss"],b["loss"],rel_tol=1e-4,abs_tol=1e-5)}
    for a,b in zip(control_report["pre_reload_pass2"], control_report["post_reload_pass2"])]
control_report["post_reload_repeats_stable"] = all(math.isclose(a["loss"],b["loss"],rel_tol=1e-4,abs_tol=1e-5)
    for a,b in zip(control_report["post_reload_pass1"], control_report["post_reload_pass2"]))
control_report["match"] = not changed_on_reload and control_report["post_reload_repeats_stable"] and all(c["match"] for c in control_report["comparisons"])
control_report["status"] = "controlled_reload_match" if control_report["match"] else "controlled_reload_mismatch"
control_report["original_failed_report_preserved"] = hashlib.sha256((SOURCE_ROOT / "reload-check.json").read_bytes()).hexdigest() == control_report["original_failed_report_sha256"]
save_control()
print(json.dumps(control_report, indent=2))
print("Saved controlled test:", CONTROL_ROOT)
if control_report["match"]:
    (CONTROL_ROOT / "CONTROL_RELOAD_MATCH").write_text("New controlled reproduction matched; original failed result retained.\n")
else:
    print("Mismatch remains. Do not start the full 10K run.")
print("Full 10K training has NOT started. This adapter contains a disposable additional update.")
