# Run in the SAME Colab session after the failed loss comparison.
# Diagnostic only: no model loading, optimizer, training, or report deletion.
from pathlib import Path
import collections
import hashlib
import json
import math
import time
import uuid
import torch
from peft import get_peft_model_state_dict
from safetensors.torch import load_file

DIAGNOSTIC_ROOT = Path("/content/drive/MyDrive/SVAGA/qwen3coder30b-preflight-v1/disposable-3f354f1b83b1")
assert globals().get("model") is not None, "Keep the current reloaded model; do not reload or retrain."
old_report_path = DIAGNOSTIC_ROOT / "reload-check.json"
old_report_bytes = old_report_path.read_bytes()
old_report = json.loads(old_report_bytes)
assert old_report["match"] is False
assert old_report["model"] == "Qwen/Qwen3-Coder-30B-A3B-Instruct"
assert getattr(model.config, "_commit_hash", None) == old_report["revision"]
assert not (DIAGNOSTIC_ROOT / "RELOAD_MATCH").exists(), "A success marker already exists; stop and review."
reference = json.loads((DIAGNOSTIC_ROOT / "reload-reference.json").read_text())
examples = reference["examples"]
assert len(examples) == 2
assert [e["task"] for e in examples] == [e["task"] for e in old_report["comparisons"]]
saved_adapter = load_file(str(DIAGNOSTIC_ROOT / "trained_adapter/adapter_model.safetensors"), device="cpu")


def state_matches_saved(current_model):
    current = get_peft_model_state_dict(current_model)
    assert set(current) == set(saved_adapter)
    for key, tensor in current.items():
        value = tensor.detach().cpu()
        assert value.dtype == saved_adapter[key].dtype and torch.equal(value, saved_adapter[key]), key
    return True


def diagnose(current_model):
    # These references remain local and are released on return.
    original_flags = [(p, p.requires_grad) for p in current_model.parameters()]
    original_training = current_model.training
    active = getattr(current_model, "active_adapters", None)
    if callable(active):
        active = active()
    report = {
        "scope": "evaluation_only_reload_mismatch_diagnostic",
        "model": old_report["model"], "revision": old_report["revision"],
        "failed_reload_report_sha256": hashlib.sha256(old_report_bytes).hexdigest(),
        "original_reload_check_passed": False,
        "active_adapters": active,
        "parameter_dtypes": dict(collections.Counter(str(p.dtype) for p in current_model.parameters())),
        "original_trainable_parameters": sum(p.numel() for p, flag in original_flags if flag),
        "config": {key: str(getattr(current_model.config, key, None)) for key in (
            "_attn_implementation", "_experts_implementation", "torch_dtype", "dtype",
            "attention_dropout", "output_router_logits", "router_aux_loss_coef",
            "num_experts_per_tok", "norm_topk_prob", "use_cache")},
        "dropout_modules": [{"name": name, "p": module.p} for name, module in current_model.named_modules()
                            if isinstance(module, torch.nn.Dropout) and module.p > 0],
        "phases": [],
        "adapter_tensors_match_before": state_matches_saved(current_model),
        "optimizer_updates": 0, "full_training_started": False,
        "limitations": [
            "Before/after reload used different requires_grad settings; test both without optimizer updates.",
            "Repeated-pass stability does not by itself prove the two fresh loads have identical quantized base state.",
            "Original failed report and numeric tolerance are preserved. No success marker is created."]}
    original_cache = current_model.config.use_cache
    try:
        # Preserve caller RNG state. Repetitions are consecutive, without reseeding between passes.
        with torch.random.fork_rng(devices=[0]):
            torch.manual_seed(42)
            torch.cuda.manual_seed_all(42)
            for phase_name, enable_lora in (("frozen_first", False), ("adapter_trainable_flags", True), ("frozen_again", False)):
                current_model.requires_grad_(False)
                if enable_lora:
                    for name, parameter in current_model.named_parameters():
                        if "lora_" in name:
                            parameter.requires_grad_(True)
                current_model.eval()
                current_model.config.use_cache = False
                trainable_names = [name for name, p in current_model.named_parameters() if p.requires_grad]
                assert not trainable_names or all("lora_" in name for name in trainable_names)
                training_modules = [name for name, module in current_model.named_modules() if module.training]
                phase = {"phase": phase_name,
                    "trainable_parameters": sum(p.numel() for p in current_model.parameters() if p.requires_grad),
                    "modules_still_training_after_eval": training_modules, "passes": []}
                print("PHASE:", phase_name, "trainable parameters:", phase["trainable_parameters"], flush=True)
                for repetition in (1, 2):
                    details = []
                    with torch.no_grad():
                        for example in examples:
                            ids = torch.tensor([example["input_ids"]], dtype=torch.long, device="cuda")
                            labels = ids.clone()
                            labels[:, :example["prompt_length"]] = -100
                            assert int((labels[:, 1:] != -100).sum()) == example["target_tokens"]
                            cpu_rng_before = torch.get_rng_state().clone()
                            gpu_rng_before = torch.cuda.get_rng_state().clone()
                            torch.cuda.synchronize()
                            started = time.perf_counter()
                            with torch.autocast("cuda", dtype=torch.bfloat16):
                                output = current_model(input_ids=ids, attention_mask=torch.ones_like(ids), labels=labels, use_cache=False)
                            value = float(output.loss.float())
                            assert math.isfinite(value)
                            torch.cuda.synchronize()
                            detail = {"task": example["task"], "loss": value,
                                "loss_dtype": str(output.loss.dtype), "output_requires_grad": output.loss.requires_grad,
                                "cpu_rng_changed": not torch.equal(cpu_rng_before, torch.get_rng_state()),
                                "cuda_rng_changed": not torch.equal(gpu_rng_before, torch.cuda.get_rng_state()),
                                "seconds": time.perf_counter() - started}
                            details.append(detail)
                            print(phase_name, "pass", repetition, example["task"], "loss:", value, flush=True)
                            del ids, labels, output
                    phase["passes"].append(details)
                phase["repeated_passes"] = [
                    {"task": a["task"], "absolute_difference": abs(a["loss"] - b["loss"]),
                     "match_at_original_tolerance": math.isclose(a["loss"], b["loss"], rel_tol=1e-4, abs_tol=1e-5)}
                    for a, b in zip(*phase["passes"])]
                phase["comparisons_to_failed_check"] = []
                for latest, previous in zip(phase["passes"][-1], old_report["comparisons"]):
                    phase["comparisons_to_failed_check"].append({
                        "task": latest["task"],
                        "difference_from_original_pre_reload_loss": latest["loss"] - previous["saved_model_loss"],
                        "difference_from_original_post_reload_loss": latest["loss"] - previous["reloaded_model_loss"],
                        "matches_original_pre_reload_loss": math.isclose(latest["loss"], previous["saved_model_loss"], rel_tol=1e-4, abs_tol=1e-5),
                        "matches_original_post_reload_loss": math.isclose(latest["loss"], previous["reloaded_model_loss"], rel_tol=1e-4, abs_tol=1e-5)})
                report["phases"].append(phase)
        report["adapter_tensors_match_after"] = state_matches_saved(current_model)
        assert all(p.grad is None for p in current_model.parameters()), "Unexpected gradients in diagnostic."
    finally:
        for parameter, original_flag in original_flags:
            parameter.requires_grad_(original_flag)
        current_model.train(original_training)
        current_model.config.use_cache = original_cache
    return report

report = diagnose(model)
assert old_report_path.read_bytes() == old_report_bytes, "Original failed report changed."
report["original_failed_report_preserved"] = True
report["requires_grad_flags_restored"] = True
output_path = DIAGNOSTIC_ROOT / ("reload-diagnostic-" + uuid.uuid4().hex[:12] + ".json")
with output_path.open("x") as stream:
    json.dump(report, stream, indent=2)
summary = {"saved": str(output_path), "original_reload_check_passed": False,
    "adapter_tensors_unchanged": report["adapter_tensors_match_before"] and report["adapter_tensors_match_after"],
    "phases": [{"phase": p["phase"], "trainable_parameters": p["trainable_parameters"],
        "modules_still_training_after_eval": p["modules_still_training_after_eval"],
        "losses": [[e["loss"] for e in pass_details] for pass_details in p["passes"]],
        "repeated_passes": p["repeated_passes"],
        "comparisons_to_failed_check": p["comparisons_to_failed_check"],
        "rng_changed_in_any_forward": any(e["cpu_rng_changed"] or e["cuda_rng_changed"] for detail in p["passes"] for e in detail)}
        for p in report["phases"]], "optimizer_updates": 0}
print(json.dumps(summary, indent=2))
print("Diagnostic saved. Failed reload result preserved; no full training started.")
