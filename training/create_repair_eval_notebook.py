"""Build an inference-only Colab notebook for the frozen development comparison."""
import ast
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    cells = []
    def md(text):
        cells.append({'cell_type': 'markdown', 'metadata': {}, 'source': text})
    def code(text):
        ast.parse(text)
        cells.append({'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [], 'source': text})
    md('# SVAGA: 20 development tasks, base versus trained adapter\n\n'
       'Inference only: no training and no execution of generated code. Use a fresh GPU runtime.\n\n'
       'Upload exactly **repair-dev20-prompts.zip** and **SVAGA_Qwen15B_10K_Final.zip**. '
       'The first contains only 20 frozen validation prompts across 12 repositories; keep private task metadata on the local machine. '
       'Both variants use the same pinned base, quantization, prompts, greedy decoding and 2,048-new-token budget. '
       'The adapter is the completed 10K QLoRA run. This is development evaluation, not Terminal-Bench.\n\n'
       'Results save to Drive after every generation. After download, local Docker execution checks reference environments and generated repairs. '
       'A successful generation is not yet a successful repair.\n')
    code('import subprocess, sys\nsubprocess.check_call([sys.executable, "-m", "pip", "install", "-q", '
         '"transformers==5.20.2", "peft==0.21.2", "accelerate==1.15.0", "bitsandbytes==0.50.2"])\n'
         'import torch\nassert torch.cuda.is_available(), "Choose a GPU runtime"\n'
         'print("PyTorch:", torch.__version__, "| GPU:", torch.cuda.get_device_name(0))\n')
    code((root/'training/repair_eval_generation.py').read_text(encoding='utf-8'))
    md('## Upload the two ZIPs\n\nDo not upload the full dataset or private_tasks.jsonl. Browser-added filename suffixes are accepted because ZIP contents and hashes are checked.\n')
    code('from google.colab import files, drive\nuploaded = files.upload()\n'
         'manifest, manifest_sha, prompts, export = load_uploads(uploaded)\ndel uploaded\n')
    code('drive.mount("/content/drive")\n'
         'RUN_ROOT = Path("/content/drive/MyDrive/SVAGA/repair-dev20-qwen15b-v1")\n'
         'print("Persistent generation output:", RUN_ROOT)\n')
    code('assert "model" not in globals(), "Use a fresh runtime or reuse the already loaded model; do not load it twice"\n'
         'model, tokenizer = load_model(manifest, export)\n')
    md('## Generate both variants\n\nForty outputs total: 20 from the base with the adapter disabled, then 20 with the adapter enabled. '
       'Greedy output is saved unchanged, including formatting errors or token-limit hits. Restarted sessions can skip completed outputs only when their run metadata matches.\n')
    code('generation_path = generate_comparison(model, tokenizer, manifest, manifest_sha, prompts, RUN_ROOT)\n')
    code('files.download(str(generation_path))\n'
         'print("Next: copy generation_results.json into the local repository and run the one-task Docker preflight.")\n')
    notebook = {'nbformat': 4, 'nbformat_minor': 5,
        'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                     'colab': {'name': 'SVAGA_Repair_Dev20_Base_vs_Adapter.ipynb'}, 'accelerator': 'GPU'},
        'cells': cells}
    for index, cell in enumerate(cells):
        cell['id'] = 'repair-dev20-' + str(index)
    out = root/'training/notebooks/SVAGA_Repair_Dev20_Base_vs_Adapter.ipynb'
    out.write_text(json.dumps(notebook, indent=2), encoding='utf-8')
    print('Created:', out)


if __name__ == '__main__':
    main()
