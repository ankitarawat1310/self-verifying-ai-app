"""Colab-only inference runtime. Generated patches are saved as text, never executed."""
from contextlib import nullcontext
from importlib.metadata import version
import hashlib
import json
from pathlib import Path, PurePosixPath
import time
import zipfile
import io
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, set_seed
from peft import PeftModel, prepare_model_for_kbit_training


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_uploads(uploaded):
    if len(uploaded) != 2:
        raise ValueError('Upload only repair-dev20-prompts.zip and SVAGA_Qwen15B_10K_Final.zip')
    public = export_raw = None
    for name, raw in uploaded.items():
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names = {item.filename for item in z.infolist() if not item.is_dir()}
            if names == {'manifest.json', 'prompts.jsonl'}:
                if public is not None:
                    raise ValueError('Duplicate prompt packet')
                public = (z.read('manifest.json'), z.read('prompts.jsonl'))
            elif {'adapter/adapter_model.safetensors', 'full_development_comparison.json'} <= names:
                if export_raw is not None:
                    raise ValueError('Duplicate adapter export')
                export_raw = raw
            else:
                raise ValueError('Unexpected ZIP contents: ' + name)
    if public is None or export_raw is None:
        raise ValueError('Need one prompt-only packet and one final adapter export')
    manifest_raw, prompts_raw = public
    manifest = json.loads(manifest_raw)
    assert manifest['evaluation_id'] == 'repair-dev20-v1' and manifest['tasks'] == 20
    assert digest(prompts_raw) == manifest['prompts_sha256']
    prompts = [json.loads(line) for line in prompts_raw.decode('utf-8').splitlines() if line.strip()]
    assert len(prompts) == len({r['instance_id'] for r in prompts}) == 20
    for row in prompts:
        assert set(row) == {'instance_id', 'repo', 'messages', 'prompt_sha256'}
        assert [m['role'] for m in row['messages']] == ['user']
        assert digest(json.dumps(row['messages'], sort_keys=True, ensure_ascii=False).encode()) == row['prompt_sha256']
    output = Path('/content/svaga-dev20-adapter')
    output.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(export_raw)) as z:
        config = json.loads(z.read('adapter/adapter_config.json'))
        assert config['base_model_name_or_path'] == manifest['model']
        trained = json.loads(z.read('results.json'))
        assert trained['model'] == manifest['model'] and trained['revision'] == manifest['model_revision']
        for name, expected in manifest['adapter_artifacts_sha256'].items():
            rel = PurePosixPath(name)
            assert not rel.is_absolute() and '..' not in rel.parts and '\\' not in name and ':' not in name
            data = z.read(name)
            assert digest(data) == expected, 'Adapter/tokenizer file hash mismatch: ' + name
            dest = output.joinpath(*rel.parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                assert dest.read_bytes() == data
            else:
                dest.write_bytes(data)
    print('Verified: 20 prompt-only development tasks; adapter/tokenizer hashes match the completed 10K run.')
    print('No reference repairs uploaded. No training or generated-command execution.')
    return manifest, digest(manifest_raw), prompts, output


def load_model(manifest, export):
    assert torch.cuda.is_available(), 'Choose a GPU runtime'
    assert manifest['model'] == 'Qwen/Qwen2.5-Coder-1.5B-Instruct'
    assert manifest['model_revision'] == '2e1fd397ee46e1388853d2af2c993145b0f1098a'
    set_seed(manifest['decoding']['seed'])
    tokenizer = AutoTokenizer.from_pretrained(str(export/'tokenizer'), local_files_only=True, trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
                              bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16)
    base = AutoModelForCausalLM.from_pretrained(manifest['model'], revision=manifest['model_revision'],
        quantization_config=quant, device_map={'': 0}, dtype=torch.float16,
        attn_implementation='sdpa', trust_remote_code=False)
    # Match the previous frozen-base preparation/casting; no optimizer is created.
    base = prepare_model_for_kbit_training(base, use_gradient_checkpointing=False)
    model = PeftModel.from_pretrained(base, str(export/'adapter'), is_trainable=False)
    model.eval()
    model.config.use_cache = True
    assert not any(p.requires_grad for p in model.parameters())
    print('Inference model ready:', manifest['model'], '| GPU:', torch.cuda.get_device_name(0))
    return model, tokenizer


def generate_comparison(model, tokenizer, manifest, manifest_sha, prompts, output_dir):
    output_dir = Path(output_dir); output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir/'generation_results.json'
    software = {name: version(name) for name in ['torch', 'transformers', 'peft', 'accelerate', 'bitsandbytes']}
    metadata = {'manifest_sha256': manifest_sha, 'model': manifest['model'],
                'revision': manifest['model_revision'], 'decoding': manifest['decoding'],
                'adapter_artifacts_sha256': manifest['adapter_artifacts_sha256'],
                'software': software, 'gpu': torch.cuda.get_device_name(0),
                'scope': 'development generation only; no tests or training executed'}
    state = json.loads(destination.read_text()) if destination.exists() else {**metadata, 'records': []}
    for key, value in metadata.items():
        assert state.get(key) == value, 'Existing run differs: ' + key + '; use a new output folder'
    saved = {(row['instance_id'], row['variant']) for row in state['records']}
    allowed_keys = {(row['instance_id'], variant) for row in prompts for variant in manifest['variants']}
    assert len(saved) == len(state['records']) and saved <= allowed_keys
    def save():
        temporary = destination.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(destination)
    model.eval()
    for variant in manifest['variants']:
        context = model.disable_adapter() if variant == 'base' else nullcontext()
        with context, torch.inference_mode():
            for row in prompts:
                if (row['instance_id'], variant) in saved:
                    continue
                encoded = tokenizer.apply_chat_template(row['messages'], tokenize=True,
                    add_generation_prompt=True, truncation=False, return_tensors='pt', return_dict=True)
                encoded = {key: value.to('cuda') for key, value in encoded.items()}
                length = encoded['input_ids'].shape[1]
                assert 0 < length <= 4096
                torch.cuda.synchronize(); started = time.perf_counter()
                with torch.autocast('cuda', dtype=torch.float16):
                    output = model.generate(**encoded, max_new_tokens=manifest['decoding']['max_new_tokens'],
                        do_sample=False, num_beams=1, use_cache=True,
                        eos_token_id=tokenizer.eos_token_id, pad_token_id=tokenizer.pad_token_id)
                torch.cuda.synchronize(); seconds = time.perf_counter()-started
                new = output[0, length:].tolist()
                limit = len(new) >= manifest['decoding']['max_new_tokens'] and (not new or new[-1] != tokenizer.eos_token_id)
                record = {'instance_id': row['instance_id'], 'variant': variant,
                          'prompt_sha256': row['prompt_sha256'],
                          'text': tokenizer.decode(new, skip_special_tokens=True),
                          'output_tokens': len(new), 'prompt_tokens': length,
                          'hit_token_limit': bool(limit), 'seconds': seconds}
                state['records'].append(record); saved.add((row['instance_id'], variant)); save()
                print(str(len(saved)) + '/40', variant, row['instance_id'], '| tokens:', len(new),
                      '| seconds:', round(seconds, 1), '| limit:', bool(limit), flush=True)
                del encoded, output
    assert len(saved) == 40
    print('Saved 40 generations:', destination)
    print('Generated text only. Download the JSON for local isolated test execution.')
    return destination
