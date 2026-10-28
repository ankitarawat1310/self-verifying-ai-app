"""Generate the Colab notebook from the reviewed runtime source."""
import ast
import hashlib
import json
from pathlib import Path
import textwrap
import argparse


def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context-enriched',action=argparse.BooleanOptionalAction,default=True,help='Use the current context-enriched v2 dataset (default).')
    args=parser.parse_args()
    runtime=(root/'training/colab_localized_repair_runtime.py').read_text(encoding='utf-8')
    ast.parse(runtime)
    cells=[]
    def md(s):cells.append({'cell_type':'markdown','metadata':{},'source':textwrap.dedent(s).strip()+'\n'})
    def code(s):
        s=textwrap.dedent(s).strip()+'\n';ast.parse(s)
        cells.append({'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':s})
    md('''
    # SVAGA: 10K localized repair fine-tuning — Qwen 1.5B
    One epoch on 10,000 official SWE-smith-derived examples, with 1,000 development-validation examples.
    This is experimental localized Python repair supervision. Inputs contain buggy patch excerpts;
    they are not complete applications. Targets reverse upstream bug patches. Only three source
    tasks were replayed locally. Missing surrounding code and semantic duplicates remain limitations.

    Use a fresh GPU runtime. Run cells in order. This starts a **fresh adapter**, separate from
    the previous 160-example terminal-action adapter. No commands in dataset text are executed.
    Model: Qwen/Qwen2.5-Coder-1.5B-Instruct; 4-bit NF4; LoRA rank 8 on q/v projections;
    learning rate 2e-5; batch size 1; accumulation 8; 1,250 optimizer updates; no truncation.
    Checkpoints go to Google Drive after update 1 and every 50 updates (400 examples).
    Loss is a prediction metric, not proof that generated repairs pass tests.
    ''')
    code('''
    import sys, subprocess, importlib.util
    import torch
    print("Python:", sys.version)
    print("PyTorch:", torch.__version__)
    assert torch.cuda.is_available(), "Select Runtime > Change runtime type > T4 GPU."
    print("GPU:", torch.cuda.get_device_name(0))
    missing = [p for p in ["transformers", "peft", "accelerate", "bitsandbytes"]
               if importlib.util.find_spec(p) is None]
    if missing:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
    import importlib.metadata
    software = {p: importlib.metadata.version(p)
                for p in ["torch", "transformers", "peft", "accelerate", "bitsandbytes"]}
    print(software)
    import bitsandbytes as bnb
    layer = bnb.nn.Linear4bit(64, 32, bias=False, quant_type="nf4").cuda()
    with torch.no_grad():
        assert layer(torch.randn(1, 64, device="cuda", dtype=torch.float16)).shape == (1, 32)
    del layer
    torch.cuda.empty_cache()
    print("4-bit GPU check passed.")
    ''')
    md('''
    ## Upload the dataset ZIP
    Select only **swesmith-localized-repair-10k-v1.zip**. This is a different package from the original
    long OpenThoughts conversations. The cell validates the ZIP contents and file hashes.
    ''')
    code('''
    from google.colab import files
    from pathlib import Path
    import io, zipfile, json, hashlib
    uploaded = files.upload()
    assert len(uploaded) == 1, "Upload only the prepared dataset ZIP."
    data_bytes = next(iter(uploaded.values()))
    dataset_dir = Path("/content/svaga-localized-10k-data")
    dataset_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data_bytes)) as archive:
        assert len(archive.namelist()) == 3
        assert set(archive.namelist()) == {"manifest.json", "train.jsonl", "validation.jsonl"}
        assert sum(x.file_size for x in archive.infolist()) < 500_000_000
        for name in archive.namelist():
            (dataset_dir / name).write_bytes(archive.read(name))
    manifest = json.loads((dataset_dir / "manifest.json").read_text())
    assert manifest["counts"] == {"train": 10000, "validation": 1000}
    for name, expected in manifest["files_sha256"].items():
        assert hashlib.sha256((dataset_dir / name).read_bytes()).hexdigest() == expected
    print("10,000 training + 1,000 validation records: hashes verified.")
    print("Status:", manifest["status"])
    del uploaded, data_bytes
    ''')
    md('''
    ## Persist checkpoints in Drive
    Keep RUN_ROOT for this experiment. For a disconnected runtime, upload the same dataset,
    set RESUME_FROM to a checkpoint folder containing COMPLETE, and rerun the setup cells.
    Only load training_state.pt files created by your own notebook.
    ''')
    code('''
    from google.colab import drive
    drive.mount("/content/drive")
    RUN_ROOT = Path("/content/drive/MyDrive/SVAGA/localized-qwen15b-10k-v1")
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    RESUME_FROM = None  # Example: str(RUN_ROOT / "step-00050")
    if RESUME_FROM is None:
        assert not list(RUN_ROOT.glob("step-*")), "Existing checkpoints: set RESUME_FROM or use a new RUN_ROOT."
    else:
        assert (Path(RESUME_FROM) / "COMPLETE").exists()
    (RUN_ROOT / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2))
    (RUN_ROOT / "software.json").write_text(json.dumps(software, indent=2))
    print("Persistent output:", RUN_ROOT)
    ''')
    code(runtime)
    code('''
    assert "model" not in globals(), "Use a fresh runtime; do not load a second model over an existing one."
    manifest, rows = load_dataset(dataset_dir)
    model, tokenizer = setup_model(RESUME_FROM)
    train_examples = prepare(rows["train"], tokenizer)
    validation_examples = prepare(rows["validation"], tokenizer)
    comparison_validation = sorted(validation_examples,
        key=lambda x: hashlib.sha256(x["task"].encode()).hexdigest())[:100]
    state = initialize_run(model, manifest, len(train_examples), RUN_ROOT, RESUME_FROM)
    print("Prepared:", len(train_examples), "training;", len(validation_examples), "development validation.")
    print("Resuming at example:", state["run"]["next_position"])
    print("No truncation. Prompt tokens are masked from loss.")
    ''')
    md('''
    ## Baseline on a fixed 100-example development subset
    The exact same 100 examples are evaluated after training. The remaining validation
    records remain available for final development evaluation; this is not a benchmark test set.
    ''')
    code('''
    if state["run"]["baseline"] is None:
        assert state["run"]["next_position"] == 0
        with model.disable_adapter():
            state["run"]["baseline"] = evaluate(model, comparison_validation)
        (RUN_ROOT / "baseline.json").write_text(json.dumps(state["run"]["baseline"], indent=2))
    print("Baseline loss:", state["run"]["baseline"]["token_weighted_loss"])
    ''')
    md('''
    ## Train one epoch
    Run this cell once. Expect a sustained run; estimates appear after the first updates.
    Keep Colab connected. If interrupted or an error occurs, start a fresh runtime and resume
    the latest COMPLETE checkpoint. Do not rerun this cell on a partially updated model.
    ''')
    code('''
    assert "training_cell_started" not in globals(), "Training was already started in this runtime. Resume from Drive in a fresh runtime."
    training_cell_started = True
    train_epoch(model, tokenizer, train_examples, state)
    ''')
    code('''
    assert state["run"]["next_position"] == 10000
    after = evaluate(model, comparison_validation)
    baseline = state["run"]["baseline"]
    results = {
        "model": MODEL_ID, "revision": REVISION,
        "training_examples": 10000, "validation_available": 1000,
        "comparison_validation_examples": 100,
        "baseline": baseline, "after": after,
        "loss_change": after["token_weighted_loss"] - baseline["token_weighted_loss"],
        "optimizer_steps": state["run"]["optimizer_steps"],
        "training_peak_gpu_gib": state["run"]["peak_gpu_memory_gib"],
        "dataset_status": manifest["status"], "software": software,
        "meaning": "Development imitation loss only; no generated patches executed."
    }
    (RUN_ROOT / "results.json").write_text(json.dumps(results, indent=2))
    final_dir = RUN_ROOT / "final_export"
    final_dir.mkdir(exist_ok=False)
    model.save_pretrained(final_dir / "adapter")
    tokenizer.save_pretrained(final_dir / "tokenizer")
    (final_dir / "results.json").write_text(json.dumps(results, indent=2))
    (final_dir / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2))
    print("Before:", baseline["token_weighted_loss"])
    print("After:", after["token_weighted_loss"])
    print("Change:", results["loss_change"])
    print("Saved:", final_dir)
    ''')
    md('''
    ## Reload check and download
    This checks the saved adapter on the same base weights. It does not independently
    reload the entire quantized base model or demonstrate successful software repairs.
    ''')
    code('''
    import math, shutil
    original_adapter = model.active_adapter
    model.load_adapter(str(final_dir / "adapter"), adapter_name="reload_check", is_trainable=False)
    try:
        model.set_adapter("reload_check")
        reloaded = evaluate(model, comparison_validation)
        difference = abs(reloaded["token_weighted_loss"] - after["token_weighted_loss"])
        assert math.isclose(reloaded["token_weighted_loss"], after["token_weighted_loss"], rel_tol=1e-5, abs_tol=1e-6)
    finally:
        model.set_adapter(original_adapter)
    (final_dir / "reload_check.json").write_text(json.dumps({"difference": difference, "match": True}, indent=2))
    print("Saved-adapter reload: MATCH; difference:", difference)
    archive = shutil.make_archive("/content/svaga-localized-qwen15b-10k-final", "zip", final_dir)
    files.download(archive)
    ''')
    md('''
    ## Optional: evaluate all 1,000 development records
    Run after the matched 100-example comparison and save. The full-set loss has no
    full-set baseline in this notebook, so do not compare it directly to the 100-example baseline.
    Actual repair quality still requires generating patches and executing tests in isolated tasks.
    ''')
    code('''
    full_validation = evaluate(model, validation_examples)
    (RUN_ROOT / "full_development_validation.json").write_text(json.dumps(full_validation, indent=2))
    print("Full development loss:", full_validation["token_weighted_loss"])
    print("Examples:", full_validation["examples"])
    ''')
    if args.context_enriched:
        for cell in cells:
            cell['source']=cell['source'].replace('swesmith-localized-repair-10k-v1.zip','swesmith-context-repair-10k-v2.zip').replace('localized-qwen15b-10k-v1','context-qwen15b-10k-v2').replace('buggy patch excerpts','buggy functions and statically selected supporting context')
        cells[0]['source']+='\nDataset v2 uses complete affected functions, class scaffolding and referenced module definitions, with repository-balanced selection. This still does not prove semantic completeness or correct generated repairs.\n'
    for i,cell in enumerate(cells):cell['id']=f'svaga-{i:03d}'
    notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
               'colab':{'name':'SVAGA_10K_Localized_Repair_Qwen15B.ipynb'},'accelerator':'GPU'},'cells':cells}
    out=root/'training/notebooks';out.mkdir(exist_ok=True)
    path=out/('SVAGA_10K_Context_Repair_Qwen15B_v2.ipynb' if args.context_enriched else 'SVAGA_10K_Localized_Repair_Qwen15B.ipynb')
    path.write_text(json.dumps(notebook,indent=2),encoding='utf-8')
    print('Notebook:',path,'code cells:',sum(c['cell_type']=='code' for c in cells))


if __name__=='__main__':main()
