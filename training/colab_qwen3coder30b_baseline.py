# SAME A100 session after CONTROL_RELOAD_MATCH.
# Restore the original zero-update adapter, then measure BASE-model dev loss.
# No optimizer is created and no weights are trained in this cell.
import hashlib, json, math, random, time
from pathlib import Path
from importlib.metadata import version
import numpy as np
import torch
from peft import get_peft_model_state_dict, set_peft_model_state_dict
from safetensors.torch import load_file

PILOT_ROOT = Path("/content/drive/MyDrive/SVAGA/qwen3coder30b-preflight-v1/disposable-3f354f1b83b1")
CONTROL_CHECK_ROOT = PILOT_ROOT / "controlled-reload-8b8ec82172ca"
assert (CONTROL_CHECK_ROOT / "CONTROL_RELOAD_MATCH").exists()
control_evidence = json.loads((CONTROL_CHECK_ROOT / "report.json").read_text())
assert control_evidence["match"] is True
assert control_evidence["frozen_base_unchanged_during_update_and_mode_transition"]
assert control_evidence["frozen_base_serialized_state_matches_across_reload"]
assert globals().get("model") is not None
assert getattr(model.config, "_commit_hash", None) == REVISION
assert MODEL_ID == "Qwen/Qwen3-Coder-30B-A3B-Instruct"
assert len(prepared["train"]) == 10000 and len(prepared["validation"]) == 1000
assert data_report["input_sha256"] == {
    "train.jsonl":"36d790d8f87c19cf2d914863cb8a3be7c1be3c2e74d5af183fd3755b0a802eec",
    "validation.jsonl":"3953a213500952e1b03f003514d36b2b5c6c661ed5a387cbc278d7d588fd02dc"}
FULL_RUN_ROOT = Path("/content/drive/MyDrive/SVAGA/context-qwen3coder30b-10k-v1")
assert not FULL_RUN_ROOT.exists(), "Run folder already exists. Do not overwrite or rerun; inspect its saved state."

pilot_report = json.loads((PILOT_ROOT / "report.json").read_text())
initial_dir = PILOT_ROOT / "initial_adapter"
for name in ("adapter_config.json", "adapter_model.safetensors"):
    expected = pilot_report["files_sha256"]["initial_adapter/" + name]
    assert hashlib.sha256((initial_dir / name).read_bytes()).hexdigest() == expected
initial_config = json.loads((initial_dir / "adapter_config.json").read_text())
assert initial_config["base_model_name_or_path"] == MODEL_ID and initial_config["revision"] == REVISION
assert initial_config["r"] == 16 and initial_config["lora_alpha"] == 16
assert initial_config["lora_dropout"] == 0 and initial_config["bias"] == "none"
assert set(initial_config["target_modules"]) == {"q_proj","k_proj","v_proj","o_proj"}
initial_state = load_file(str(initial_dir / "adapter_model.safetensors"), device="cpu")
assert initial_state and all("lora_" in key for key in initial_state)
initial_b = [value for key, value in initial_state.items() if "lora_B" in key]
assert initial_b and all(torch.count_nonzero(value).item() == 0 for value in initial_b)
current_state = get_peft_model_state_dict(model)
assert set(current_state) == set(initial_state)
assert all(current_state[key].shape == value.shape and current_state[key].dtype == value.dtype for key,value in initial_state.items())
del current_state
outcome = set_peft_model_state_dict(model, initial_state, adapter_name="default")
assert not outcome.unexpected_keys and not any("lora_" in key for key in outcome.missing_keys)
assert all(torch.equal(t.detach().cpu(), initial_state[key]) for key,t in get_peft_model_state_dict(model).items())
model.requires_grad_(False)
model.eval(); model.config.use_cache = False
model.peft_config["default"].revision = REVISION
random.seed(42); np.random.seed(42); torch.manual_seed(42); torch.cuda.manual_seed_all(42)
# Use the tokenizer returned by the successful fresh controlled load.
tokenizer = getattr(control_tokenizer, "tokenizer", control_tokenizer)
assert hashlib.sha256(json.dumps(tokenizer.chat_template,sort_keys=True).encode()).hexdigest() == data_report["chat_template_sha256"]
comparison_validation = sorted(prepared["validation"], key=lambda e:hashlib.sha256(e["task"].encode()).hexdigest())[:100]
assert len(comparison_validation) == 100
assert not {e["task"] for e in prepared["train"]} & {e["task"] for e in comparison_validation}

FULL_RUN_ROOT.mkdir(exist_ok=False)
software = {p:version(p) for p in ("torch","transformers","peft","accelerate","bitsandbytes","unsloth","unsloth_zoo")}
full_run_config = {
    "experiment":"context-qwen3coder30b-10k-v1", "model":MODEL_ID, "revision":REVISION,
    "software":software, "seed":42, "train_records":10000, "validation_records":1000,
    "input_sha256":data_report["input_sha256"], "chat_template_sha256":data_report["chat_template_sha256"],
    "initial_adapter_source_sha256":pilot_report["files_sha256"]["initial_adapter/adapter_model.safetensors"],
    "controlled_reload_report_sha256":hashlib.sha256((CONTROL_CHECK_ROOT / "report.json").read_bytes()).hexdigest(),
    "original_reload_failed_report_preserved":str(PILOT_ROOT / "reload-check.json"),
    "planned_training":{"epochs":1,"optimizer":"AdamW","learning_rate":2e-5,"weight_decay":0,
        "microbatch":1,"gradient_accumulation":8,"optimizer_updates":1250,
        "gradient_clip":1.0,"max_tokens":4096,"dtype":"bfloat16", "prompt_labels":-100,
        "gradient_objective":"mean of per-example mean target-token losses within each group of eight",
        "lora":{"r":16,"alpha":16,"dropout":0,"target_modules":["q_proj","k_proj","v_proj","o_proj"],"bias":"none"}},
    "full_training_started":False,
    "data_status":manifest["status"],
    "baseline_scope":"same SHA-ordered 100 development task IDs as the 1.5B subset; native 30B tokenization",
    "limitations":["Experimental localized-repair targets with oracle affected locations; not verified secure-application data.",
        "Loss is target prediction, not executed repair accuracy or a Terminal-Bench score.",
        "1.5B used a different adapter/runtime configuration; cross-model scores are not an isolated architecture-only ablation.",
        "Original failed reload is preserved; a separate fingerprinted controlled reproduction passed.",
        "Frozen dev20 executable base generation is still pending and must precede full training."]}
(FULL_RUN_ROOT / "config.json").write_text(json.dumps(full_run_config,indent=2))
(FULL_RUN_ROOT / "dataset_manifest.json").write_text(json.dumps(manifest,indent=2))
(FULL_RUN_ROOT / "baseline-validation-ids.json").write_text(json.dumps([e["task"] for e in comparison_validation],indent=2))
model.save_pretrained(FULL_RUN_ROOT / "initial_adapter",safe_serialization=True)
tokenizer.save_pretrained(FULL_RUN_ROOT / "tokenizer")
saved_initial_state = load_file(str(FULL_RUN_ROOT / "initial_adapter/adapter_model.safetensors"),device="cpu")
assert set(saved_initial_state) == set(initial_state)
assert all(saved_initial_state[key].dtype == value.dtype and torch.equal(saved_initial_state[key], value) for key,value in initial_state.items())
print("Original untrained adapter restored exactly. No pilot updates carried into this run.",flush=True)
print("Evaluating the BASE model on 100 development records...",flush=True)
started=time.perf_counter(); total=0.; target_count=0; details=[]
model.eval(); model.config.use_cache=False
torch.cuda.reset_peak_memory_stats()
with model.disable_adapter(), torch.no_grad():
    for number,example in enumerate(comparison_validation,1):
        ids=torch.tensor([example["input_ids"]],dtype=torch.long,device="cuda")
        labels=ids.clone(); labels[:,:example["prompt_length"]]=-100
        count=int((labels[:,1:]!=-100).sum()); assert count==example["target_tokens"]>0
        with torch.autocast("cuda",dtype=torch.bfloat16):
            output=model(input_ids=ids,attention_mask=torch.ones_like(ids),labels=labels,use_cache=False)
        value=float(output.loss.float()); assert math.isfinite(value)
        total+=value*count; target_count+=count
        details.append({"task":example["task"],"loss":value,"target_tokens":count})
        if number%10==0: print("Baseline:",number,"/ 100",flush=True)
        del ids,labels,output
baseline_30b={"scope":"base_model_development_subset_prediction_loss","model":MODEL_ID,"revision":REVISION,
    "adapter_mode":"disabled", "examples":100,"target_tokens":target_count,
    "token_weighted_loss":total/target_count,"details":details,"seconds":time.perf_counter()-started,
    "peak_allocated_gpu_gib":torch.cuda.max_memory_allocated()/2**30,
    "optimizer_updates":0,"full_training_started":False}
with (FULL_RUN_ROOT / "baseline.json").open("x") as stream: json.dump(baseline_30b,stream,indent=2)
(FULL_RUN_ROOT / "BASELINE_COMPLETE").write_text("Untrained adapter restored and 100-record base development loss recorded; no optimizer updates.\n")
print("Baseline token-weighted validation loss:",baseline_30b["token_weighted_loss"])
print("Saved:",FULL_RUN_ROOT)
print("No optimizer updates. Next: frozen executable dev20 base generations, then the separately checkpointed 10K run.")
