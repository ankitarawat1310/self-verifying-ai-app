"""Freeze development tasks and a prompt-only Colab package from local pinned data."""
import argparse
from collections import Counter
import json
from pathlib import Path
import zipfile
try:
    from .repair_eval_common import MODEL_ID, MODEL_REVISION, SOURCE_REVISION, SELECTION_SEED, sha, select_tasks, patch_paths, selector_key, normalize_official_selector
except ImportError:
    from repair_eval_common import MODEL_ID, MODEL_REVISION, SOURCE_REVISION, SELECTION_SEED, sha, select_tasks, patch_paths, selector_key, normalize_official_selector


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=root/'data/evaluation/repair-dev20-v1')
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Frozen evaluation exists; choose a new version instead of overwriting it')
    package = root/'data/prepared/swesmith-context-repair-10k-v2'
    manifest = json.loads((package/'manifest.json').read_text())
    raw = (package/'validation.jsonl').read_bytes()
    assert sha(raw) == manifest['files_sha256']['validation.jsonl']
    rows = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    assert len(rows) == 1000
    selected = select_tasks(rows)
    wanted = {row['instance_id']: row for row in selected}
    # Existing cache only: preparing the packet does not download images or run tasks.
    from huggingface_hub import snapshot_download
    import pyarrow.parquet as pq
    snapshot = Path(snapshot_download('SWE-bench/SWE-smith-py', repo_type='dataset',
                                     revision=SOURCE_REVISION, local_files_only=True))
    official = {}
    columns = ['instance_id', 'repo', 'patch', 'FAIL_TO_PASS', 'PASS_TO_PASS', 'image_name']
    for shard in sorted(snapshot.rglob('*.parquet')):
        for batch in pq.ParquetFile(shard).iter_batches(batch_size=128, columns=columns):
            for row in batch.to_pylist():
                if row['instance_id'] in wanted:
                    official[row['instance_id']] = row
    assert set(official) == set(wanted)
    private = []
    prompts = []
    for row in selected:
        task = official[row['instance_id']]
        assert task['repo'] == row['repo'] and task['image_name'] == row['image_name']
        assert sha(task['patch']) == row['bug_patch_sha256']
        allowed = sorted(patch_paths(task['patch']))
        selectors = task['FAIL_TO_PASS'] + task['PASS_TO_PASS']
        assert task['FAIL_TO_PASS'] and selectors and len(set(selectors)) == len(selectors)
        for selector in selectors:
            selector_key(normalize_official_selector(selector, task['repo']))
        messages = row['messages'][:1]
        assert len(messages) == 1 and messages[0]['role'] == 'user'
        prompt_hash = sha(json.dumps(messages, sort_keys=True, ensure_ascii=False))
        prompts.append({'instance_id': row['instance_id'], 'repo': row['repo'],
                        'messages': messages, 'prompt_sha256': prompt_hash})
        private.append({**task, 'allowed_paths': allowed, 'prompt_sha256': prompt_hash,
                        'source_revision': SOURCE_REVISION})
    export = root/'results/fine_tuning/qwen15b-context-10k-v2'
    artifacts = ['adapter/adapter_model.safetensors', 'adapter/adapter_config.json',
                 'tokenizer/tokenizer.json', 'tokenizer/tokenizer_config.json', 'tokenizer/chat_template.jinja']
    adapter_hashes = {name: sha((export/name).read_bytes()) for name in artifacts}
    output = args.output
    output.mkdir(parents=True)
    public = output/'public'; public.mkdir()
    def jsonl(items):
        return ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in items).encode('utf-8')
    data = jsonl(prompts)
    public_manifest = {'evaluation_id': 'repair-dev20-v1', 'scope': 'development_only_not_external_benchmark',
        'selection': 'fixed SHA256 order and round-robin across validation repositories; no output-based selection',
        'selection_seed': SELECTION_SEED, 'tasks': 20,
        'repositories': dict(Counter(row['repo'] for row in selected)),
        'source_validation_sha256': sha(raw), 'prompts_sha256': sha(data),
        'private_tasks_sha256': sha(jsonl(private)),
        'model': MODEL_ID, 'model_revision': MODEL_REVISION, 'adapter_artifacts_sha256': adapter_hashes,
        'decoding': {'do_sample': False, 'num_beams': 1, 'max_new_tokens': 2048, 'seed': 42},
        'variants': ['base', 'adapter'],
        'limitations': ['Already used development validation, not an untouched test set.',
                        'Affected source locations are supplied; no repository-search evaluation.',
                        'No reference answers, bug patches, test selectors or oracle code in this upload.']}
    (public/'prompts.jsonl').write_bytes(data)
    (public/'manifest.json').write_text(json.dumps(public_manifest, indent=2), encoding='utf-8')
    (output/'private_tasks.jsonl').write_bytes(jsonl(private))
    with zipfile.ZipFile(output/'repair-dev20-prompts.zip', 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for name in ['manifest.json', 'prompts.jsonl']:
            z.write(public/name, name)
    print('Frozen packet:', output)
    print('Tasks:', len(prompts), 'repositories:', len(public_manifest['repositories']))
    print('Upload only repair-dev20-prompts.zip plus the final model export ZIP to Colab.')
    print('Keep private_tasks.jsonl on the local evaluation machine.')


if __name__ == '__main__':
    main()
