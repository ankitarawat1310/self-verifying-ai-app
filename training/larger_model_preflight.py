"""Read-only hardware probe or CPU tokenizer audit; never loads model weights."""
import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys

MODEL_ID = "Qwen/Qwen3-Coder-30B-A3B-Instruct"
REVISION = "b2cff646eb4bb1d68355c01b18ae02e7cf42d120"
EXPECTED = {
    "train.jsonl": "36d790d8f87c19cf2d914863cb8a3be7c1be3c2e74d5af183fd3755b0a802eec",
    "validation.jsonl": "3953a213500952e1b03f003514d36b2b5c6c661ed5a387cbc278d7d588fd02dc",
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def hardware_report():
    software = {}
    for package in ("torch", "transformers", "peft", "accelerate", "bitsandbytes", "unsloth", "unsloth_zoo"):
        try:
            software[package] = version(package)
        except PackageNotFoundError:
            software[package] = None
    report = {
        "scope": "hardware_probe_only_no_model_loading_or_training",
        "utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version, "platform": platform.platform(),
        "software": software,
        "disk_free_gib": round(shutil.disk_usage(Path.cwd()).free / 2**30, 2),
        "candidate_model": MODEL_ID,
        "candidate_status": "provisional_pending_hardware_and_real_data_preflight",
        "gpus": [],
    }
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        values = dict(line.split(":", 1) for line in meminfo.read_text().splitlines())
        report["host_ram_total_gib"] = round(int(values["MemTotal"].split()[0]) / 2**20, 2)
        report["host_ram_available_gib"] = round(int(values["MemAvailable"].split()[0]) / 2**20, 2)
    try:
        import torch
        report["torch_cuda"] = torch.version.cuda
        report["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            for index in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(index)
                free, total = torch.cuda.mem_get_info(index)
                report["gpus"].append({
                    "index": index, "name": props.name,
                    "total_gib": round(total / 2**30, 2),
                    "free_gib": round(free / 2**30, 2),
                    "allocated_gib": round(torch.cuda.memory_allocated(index) / 2**30, 2),
                    "compute_capability": list(torch.cuda.get_device_capability(index)),
                })
    except Exception as exc:
        report["torch_probe_error"] = type(exc).__name__ + ": " + str(exc)
    try:
        proc = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version", "--format=csv,noheader"], capture_output=True, text=True, timeout=15)
        report["nvidia_smi"] = proc.stdout.strip() if proc.returncode == 0 else proc.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        report["nvidia_smi_error"] = str(exc)
    largest = max((g["total_gib"] for g in report["gpus"]), default=0)
    # A screening threshold, not a memory-fit guarantee. Never combine GPU capacities here.
    report["next_action"] = (
        "STOP: no usable PyTorch CUDA device detected. Check the software/GPU report before downloading weights."
        if largest == 0 else
        "STOP: below the 22 GiB screening threshold for reproducing the recorded 4090 setup. Do not load the 30B candidate in this runtime."
        if largest < 22 else
        "Hardware screen passed only. Review RAM, free VRAM, disk, software and the tokenizer audit before a separate real-data loading/backward/save/reload preflight."
    )
    report["limitations"] = [
        "No model weights downloaded, no package installs and no optimizer updates.",
        "22 GiB is a conservative screening policy based on local lab observations, not an official minimum or proof of fit.",
        "Synthetic lab timings are not real-data throughput estimates.",
    ]
    return report


def audit_dataset(data_dir):
    from transformers import AutoTokenizer
    data_dir = Path(data_dir)
    for name, expected in EXPECTED.items():
        if digest(data_dir / name) != expected:
            raise ValueError("Frozen dataset hash mismatch: " + name)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=REVISION,
        local_files_only=True, trust_remote_code=False)
    report = {
        "scope": "cpu_only_tokenizer_audit_no_weights_no_truncation",
        "model": MODEL_ID, "revision": REVISION,
        "transformers": version("transformers"), "input_sha256": EXPECTED,
        "chat_template_sha256": hashlib.sha256(json.dumps(tokenizer.chat_template, sort_keys=True).encode()).hexdigest(),
        "template_options": {"add_generation_prompt": False, "truncation": False},
        "splits": {},
        "limitations": ["Token counts do not establish GPU fit or repair correctness.",
            "Frozen records, task IDs, targets and splits were not changed.",
            "Model selection is provisional until the actual GPU and real-data preflight are checked."],
    }
    for split, expected_count in (("train", 10000), ("validation", 1000)):
        rows, identifiers = [], set()
        with (data_dir / (split + ".jsonl")).open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                identifier = row["instance_id"]
                if identifier in identifiers:
                    raise ValueError("Duplicate task ID: " + identifier)
                identifiers.add(identifier)
                ids = tokenizer.apply_chat_template(row["messages"], tokenize=True,
                    add_generation_prompt=False, truncation=False, return_dict=False)
                if not isinstance(ids, list) or not ids or not all(isinstance(n, int) for n in ids):
                    raise TypeError("Unexpected tokenizer result for " + identifier)
                rows.append({"line": line_number, "instance_id": identifier, "tokens": len(ids)})
                if len(rows) % 1000 == 0:
                    print(split + ": " + str(len(rows)) + " tokenized", flush=True)
        if len(rows) != expected_count:
            raise ValueError("Unexpected record count for " + split)
        lengths = [r["tokens"] for r in rows]
        report["splits"][split] = {
            "records": len(rows), "minimum": min(lengths), "median": statistics.median(lengths),
            "maximum": max(lengths), "total_tokens": sum(lengths),
            "fits": {str(cap): sum(n <= cap for n in lengths) for cap in (4096, 8192, 16384)},
            "rows": rows,
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("hardware", "audit"))
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Existing report preserved; choose a new output path")
    if args.mode == "audit" and args.data_dir is None:
        parser.error("audit requires --data-dir")
    report = hardware_report() if args.mode == "hardware" else audit_dataset(args.data_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    lean = {k: v for k, v in report.items() if k != "splits"}
    if "splits" in report:
        lean["splits"] = {k: {key: value for key, value in v.items() if key != "rows"} for k, v in report["splits"].items()}
    print(json.dumps(lean, indent=2))
    print("Saved:", args.output)


if __name__ == "__main__":
    main()
