# Run in the restarted A100 Colab session, after the successful GPU check.
import unsloth
from unsloth import FastModel
import torch
from pathlib import Path
from importlib.metadata import version
from google.colab import drive
import json
import time

MODEL_ID = "Qwen/Qwen3-Coder-30B-A3B-Instruct"
REVISION = "b2cff646eb4bb1d68355c01b18ae02e7cf42d120"
assert torch.cuda.is_available()
assert torch.cuda.get_device_properties(0).total_memory / 2**30 >= 35
assert globals().get("model") is None, "A model is already loaded; do not load a duplicate."

drive.mount("/content/drive")
RUN_ROOT = Path("/content/drive/MyDrive/SVAGA/qwen3coder30b-preflight-v1")
RUN_ROOT.mkdir(parents=True, exist_ok=True)
attempt = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
software = {p: version(p) for p in ["torch", "transformers", "peft", "accelerate", "bitsandbytes", "unsloth", "unsloth_zoo"]}
setup = {"model": MODEL_ID, "revision": REVISION, "software": software,
    "scope": "model_loading_preflight_only", "max_seq_length": 4096,
    "quantization": "4bit_by_unsloth_from_exact_official_model", "dtype": "bfloat16",
    "attention_note": "xformers mismatch reported; PyTorch attention fallback",
    "full_training_started": False}
with (RUN_ROOT / ("setup-" + attempt + ".json")).open("x") as stream:
    json.dump(setup, stream, indent=2)

torch.cuda.reset_peak_memory_stats()
started = time.time()
model, tokenizer = FastModel.from_pretrained(
    model_name=MODEL_ID,
    revision=REVISION,
    use_exact_model_name=True,
    max_seq_length=4096,
    dtype=torch.bfloat16,
    load_in_4bit=True,
    full_finetuning=False,
    device_map={"": 0},
    trust_remote_code=False,
)
observed_revision = getattr(model.config, "_commit_hash", None)
assert observed_revision == REVISION, f"Model revision not confirmed: {observed_revision}"
assert getattr(model, "is_loaded_in_4bit", False), "4-bit loading was not confirmed"
report = {**setup, "observed_model_revision": observed_revision,
    "gpu": torch.cuda.get_device_name(0),
    "load_seconds": round(time.time() - started, 1),
    "allocated_gpu_gib": round(torch.cuda.memory_allocated() / 2**30, 2),
    "peak_gpu_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2),
    "loaded_in_4bit": bool(model.is_loaded_in_4bit),
    "training_performed": False, "adapter_attached": False}
with (RUN_ROOT / ("load-report-" + attempt + ".json")).open("x") as stream:
    json.dump(report, stream, indent=2)
print(json.dumps(report, indent=2))
print("Model loaded. No LoRA adapter attached and no training performed.")
