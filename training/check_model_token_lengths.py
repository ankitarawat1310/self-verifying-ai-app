"""CPU-only tokenizer audit for prepared messages JSONL; no weights or truncation."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
from importlib.metadata import version

MODELS = [
    ("Qwen/Qwen3-Coder-30B-A3B-Instruct", 24576),
    ("Qwen/Qwen3.6-27B", 16384),
    ("unsloth/gpt-oss-20b-unsloth-bnb-4bit", 8192),
    ("mistralai/Devstral-Small-2-24B-Instruct-2512", None),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new report path; existing reports are preserved")
    from huggingface_hub import HfApi
    from transformers import AutoTokenizer
    prefix = "full" if args.full else "pilot"
    paths = [args.data_dir / f"{prefix}.{split}.jsonl" for split in ("train", "validation")]
    report = {"scope": prefix, "transformers_version": version("transformers"),
              "inputs": {}, "models": {}, "notes": [
                  "No model weights loaded. No training, truncation, filtering or source-file changes.",
                  "Counts include the default tokenizer chat template; not assistant-only supervised token counts.",
                  "Lab caps came from dummy training, not proven real-data capacity. Devstral has no successful lab cap.",
                  "Explicit thinking/template options in final training may change counts."]}
    for path in paths:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1048576), b""):
                digest.update(block)
        report["inputs"][path.name] = digest.hexdigest()

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    for name, cap in MODELS:
        entry = {"dummy_training_cap": cap, "splits": {}}
        report["models"][name] = entry
        try:
            revision = HfApi().model_info(name).sha
            entry["revision"] = revision
            options = {"fix_mistral_regex": True} if name.startswith("mistralai/") else {}
            entry["tokenizer_options"] = options
            tokenizer = AutoTokenizer.from_pretrained(name, revision=revision, trust_remote_code=False, **options)
            entry["tokenizer_class"] = type(tokenizer).__name__
            entry["chat_template_sha256"] = hashlib.sha256(json.dumps(tokenizer.chat_template, sort_keys=True).encode()).hexdigest()
            for path in paths:
                lengths, errors, rows = [], [], []
                with path.open(encoding="utf-8") as stream:
                    for number, line in enumerate(stream, 1):
                        if not line.strip():
                            continue
                        row = json.loads(line)
                        try:
                            ids = tokenizer.apply_chat_template(row["messages"], tokenize=True,
                                      add_generation_prompt=False, truncation=False, return_dict=False)
                            if isinstance(ids, dict):
                                ids = ids["input_ids"]
                            length = len(ids)
                            lengths.append(length)
                            rows.append({"line": number, "task": row["task"], "tokens": length})
                        except Exception as exc:
                            errors.append({"line": number, "task": row.get("task"), "error": str(exc)})
                ordered = sorted(lengths)
                stats = {"measured": len(lengths), "errors": errors,
                         "median": statistics.median(lengths) if lengths else None,
                         "p90": ordered[round((len(ordered)-1)*0.9)] if ordered else None,
                         "maximum": max(lengths, default=None), "total_tokens": sum(lengths),
                         "fits_8192": sum(n <= 8192 for n in lengths),
                         "fits_dummy_cap": sum(n <= cap for n in lengths) if cap else None,
                         "rows": rows}
                entry["splits"][path.name] = stats
                print(name, path.name, json.dumps({k:v for k,v in stats.items() if k not in ("rows", "errors")}), flush=True)
        except Exception as exc:
            entry["load_error"] = str(exc)
            print(name, "LOAD ERROR", str(exc), flush=True)
        save()
    print("Report:", args.output, flush=True)


if __name__ == "__main__":
    main()
