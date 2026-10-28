# SAME A100 Colab session, after the successful frozen-data check.
# Two disposable training updates only; this is NOT the full 10K run.
import gc
import hashlib
import json
import math
from pathlib import Path
import time
import uuid
import torch
from unsloth import FastModel
from peft import get_peft_model_state_dict

assert globals().get("prepared") is not None, "Run the data preparation cell first."
assert len(prepared["train"]) == 10000 and len(prepared["validation"]) == 1000
assert len(preflight_examples) == 2
assert getattr(model.config, "_commit_hash", None) == REVISION
assert not getattr(model, "peft_config", None), "An adapter already exists. Do not rerun this cell."
assert not globals().get("preflight_training_started", False), "This test has already started. Stop and review."
train_tasks = {e["task"] for e in prepared["train"]}
val_tasks = {e["task"] for e in prepared["validation"]}
assert all(e["task"] in train_tasks and e["task"] not in val_tasks for e in preflight_examples)
assert max(len(e["input_ids"]) for e in preflight_examples) == 4073

PREFLIGHT_ROOT = RUN_ROOT / ("disposable-" + uuid.uuid4().hex[:12])
PREFLIGHT_ROOT.mkdir(exist_ok=False)
preflight_training_started = True
preflight_report = {
    "scope": "two_train_only_real_data_updates_not_full_training",
    "model": MODEL_ID, "revision": REVISION, "software": software,
    "seed": 42, "learning_rate": 2e-5, "microbatch": 1,
    "accumulation": 1, "optimizer": "AdamW", "weight_decay": 0,
    "dtype": "bfloat16", "gradient_clip": 1.0,
    "lora": {"r":16, "alpha":16, "dropout":0,
        "target_modules":["q_proj","k_proj","v_proj","o_proj"], "bias":"none"},
    "examples": [{"task": e["task"], "total_tokens": len(e["input_ids"]),
                  "target_tokens": e["target_tokens"]} for e in preflight_examples],
    "updates": [], "full_training_started": False,
    "limitations": ["Two fitting updates do not prove full-run stability or repair accuracy.",
        "Losses here use training examples and are not validation/evaluation scores.",
        "This adapter is disposable; the full run must start from fresh initial adapter state and a new optimizer.",
        "Persistence/reload verification is a separate next step."]}

def save_preflight_report():
    (PREFLIGHT_ROOT / "report.json").write_text(json.dumps(preflight_report, indent=2))

save_preflight_report()
model = FastModel.get_peft_model(
    model, r=16, lora_alpha=16, lora_dropout=0, bias="none",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    use_gradient_checkpointing="unsloth", random_state=42,
)
model.config.use_cache = False
trainable_named = [(name, p) for name, p in model.named_parameters() if p.requires_grad]
assert trainable_named and all("lora_" in name for name, p in trainable_named), "Unexpected non-LoRA trainable weights."
trainable = [p for name, p in trainable_named]
model.print_trainable_parameters()
preflight_report["trainable_parameters"] = sum(p.numel() for p in trainable)

# Preserve the untrained adapter separately so the pilot is never mistaken for a full run.
initial_adapter_state = {k: v.detach().cpu().clone() for k, v in get_peft_model_state_dict(model).items()}
assert initial_adapter_state
assert all(torch.count_nonzero(v).item() == 0 for k, v in initial_adapter_state.items() if "lora_B" in k)
model.peft_config["default"].revision = REVISION
model.save_pretrained(PREFLIGHT_ROOT / "initial_adapter", safe_serialization=True)
tokenizer.save_pretrained(PREFLIGHT_ROOT / "tokenizer")
preflight_report["initial_adapter_saved"] = True
save_preflight_report()

preflight_optimizer = torch.optim.AdamW(trainable, lr=2e-5, weight_decay=0)
model.train()
gc.collect()
torch.cuda.empty_cache()
torch.cuda.reset_peak_memory_stats()
try:
    for number, example in enumerate(preflight_examples, 1):
        print(f"Starting disposable update {number}/2: {len(example['input_ids'])} tokens", flush=True)
        torch.cuda.synchronize()
        started = time.perf_counter()
        preflight_optimizer.zero_grad(set_to_none=True)
        ids = torch.tensor([example["input_ids"]], dtype=torch.long, device="cuda")
        labels = ids.clone()
        labels[:, :example["prompt_length"]] = -100
        target_count = int((labels[:, 1:] != -100).sum().item())
        assert target_count == example["target_tokens"] > 0
        with torch.autocast("cuda", dtype=torch.bfloat16):
            output = model(input_ids=ids, attention_mask=torch.ones_like(ids), labels=labels, use_cache=False)
            loss = output.loss
        assert torch.isfinite(loss).item(), "Nonfinite training loss."
        loss_value = float(loss.detach().float())
        loss.backward()
        norm = torch.nn.utils.clip_grad_norm_(trainable, 1.0, error_if_nonfinite=True)
        assert math.isfinite(float(norm)) and float(norm) > 0, "Missing or invalid adapter gradients."
        assert all(p.grad is None for name, p in model.named_parameters() if not p.requires_grad), "Unexpected frozen-weight gradient."
        preflight_optimizer.step()
        assert all(torch.isfinite(p).all().item() for p in trainable), "Nonfinite updated adapter weights."
        torch.cuda.synchronize()
        item = {"step": number, "task": example["task"], "tokens": len(example["input_ids"]),
            "target_tokens": target_count, "loss": loss_value, "gradient_norm_before_clipping": float(norm),
            "seconds": time.perf_counter() - started,
            "peak_allocated_gpu_gib": torch.cuda.max_memory_allocated() / 2**30,
            "peak_reserved_gpu_gib": torch.cuda.max_memory_reserved() / 2**30}
        preflight_report["updates"].append(item)
        save_preflight_report()
        print(json.dumps(item, indent=2), flush=True)
        del ids, labels, output, loss
        preflight_optimizer.zero_grad(set_to_none=True)
    changed = any(not torch.equal(initial_adapter_state[k], v.detach().cpu())
                  for k, v in get_peft_model_state_dict(model).items())
    assert changed, "No adapter weights changed."
    preflight_report["adapter_weights_changed"] = True
    model.save_pretrained(PREFLIGHT_ROOT / "trained_adapter", safe_serialization=True)
    preflight_report["trained_adapter_saved"] = True
    saved_files = [p for folder in ("initial_adapter", "trained_adapter", "tokenizer")
                   for p in (PREFLIGHT_ROOT / folder).rglob("*") if p.is_file()]
    preflight_report["files_sha256"] = {
        str(p.relative_to(PREFLIGHT_ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in saved_files}
    preflight_report["status"] = "two_updates_completed_reload_not_yet_checked"
    save_preflight_report()
    (PREFLIGHT_ROOT / "TRAINING_COMPLETE").write_text("Two disposable updates saved; reload check still pending.\n")
except Exception as exc:
    preflight_report["status"] = "stopped_on_error"
    preflight_report["error"] = type(exc).__name__ + ": " + str(exc)
    save_preflight_report()
    raise
finally:
    preflight_optimizer.zero_grad(set_to_none=True)
    model.eval()
    del preflight_optimizer
    gc.collect()
    torch.cuda.empty_cache()
print("Disposable updates completed:", len(preflight_report["updates"]))
print("Saved:", PREFLIGHT_ROOT)
print("This is not the full 10K run. Next: independently verify saved-adapter restoration.")
