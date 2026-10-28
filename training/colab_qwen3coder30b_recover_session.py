# Run FIRST in the restarted, pinned-package A100 session.
# Restores saved artifacts and frozen data; performs NO training or new evaluations.
import unsloth
from unsloth import FastModel
import hashlib, io, json, re, time, uuid, zipfile
from pathlib import Path
from importlib.metadata import version
import torch
from peft import get_peft_model_state_dict, set_peft_model_state_dict
from safetensors.torch import load_file
from google.colab import drive, files

assert globals().get('model') is None,'A model is already loaded. Do not load a duplicate; share the current status.'
expected_software={'torch':'2.11.0+cu130','transformers':'5.17.0','peft':'0.21.2','accelerate':'1.15.0',
    'bitsandbytes':'0.50.2','unsloth':'2026.10.9','unsloth_zoo':'2026.10.9'}
software={p:version(p) for p in expected_software}
assert software==expected_software,'Package versions differ: '+json.dumps(software)
assert version('triton')=='3.6.0'
assert torch.cuda.is_available() and torch.cuda.get_device_properties(0).total_memory/2**30>=35
print('Software verified. GPU:',torch.cuda.get_device_name(0),flush=True)
drive.mount('/content/drive')
FULL_RUN_ROOT=Path('/content/drive/MyDrive/SVAGA/context-qwen3coder30b-10k-v1')
assert FULL_RUN_ROOT.is_dir(),'Saved run folder not found in this Drive account. Stop before creating a different run.'
run_plan=json.loads((FULL_RUN_ROOT/'config.json').read_text())
MODEL_ID='Qwen/Qwen3-Coder-30B-A3B-Instruct'
REVISION='b2cff646eb4bb1d68355c01b18ae02e7cf42d120'
assert run_plan['model']==MODEL_ID and run_plan['revision']==REVISION and run_plan['software']==software
assert (FULL_RUN_ROOT/'BASELINE_COMPLETE').exists()
assert (FULL_RUN_ROOT/'dev20-base/GENERATION_COMPLETE').exists()
generation_path=FULL_RUN_ROOT/'dev20-base/qwen3coder30b_dev20_base_generations.json'
assert hashlib.sha256(generation_path.read_bytes()).hexdigest()=='c18170d7dc6c1b1be567c7b48ea3b19677fdb25c5b0462aec2a8250feaee7c28','Saved base outputs changed; stop.'
generation_data=json.loads(generation_path.read_text())
assert len(generation_data['records'])==20 and all(r['variant']=='base' for r in generation_data['records'])
print('Saved baseline and all 20 original base generations verified.',flush=True)

complete_steps=sorted([p for p in FULL_RUN_ROOT.glob('step-*') if p.is_dir() and re.fullmatch(r'step-\d{5}',p.name)
    and (p/'COMPLETE').exists()],key=lambda p:int(p.name[5:]))
RECOVERY_CHECKPOINT_30B=complete_steps[-1] if complete_steps else None
prior_updates=0
if RECOVERY_CHECKPOINT_30B is not None:
    assert RECOVERY_CHECKPOINT_30B.resolve().parent==FULL_RUN_ROOT.resolve()
    runtime_config=json.loads((FULL_RUN_ROOT/'training-runtime-config.json').read_text())
    assert runtime_config['runtime_id']=='qwen3coder30b-context10k-bf16-adamw-v1'
    assert runtime_config['software']==software and runtime_config['model']==MODEL_ID and runtime_config['revision']==REVISION
    runtime_fingerprint=hashlib.sha256(json.dumps(runtime_config,sort_keys=True).encode()).hexdigest()
    checkpoint_meta=json.loads((RECOVERY_CHECKPOINT_30B/'checkpoint_manifest.json').read_text())
    assert checkpoint_meta['runtime_fingerprint']==runtime_fingerprint
    assert checkpoint_meta['optimizer_updates']==int(RECOVERY_CHECKPOINT_30B.name[5:])
    assert checkpoint_meta['next_position']==8*checkpoint_meta['optimizer_updates']
    assert {'training_state.pt','adapter/adapter_config.json','adapter/adapter_model.safetensors'}<=set(checkpoint_meta['files_sha256'])
    print('Verifying latest complete checkpoint:',RECOVERY_CHECKPOINT_30B.name,flush=True)
    for relative,expected_sha in checkpoint_meta['files_sha256'].items():
        rel=Path(relative);assert not rel.is_absolute() and '..' not in rel.parts
        assert hashlib.sha256((RECOVERY_CHECKPOINT_30B/rel).read_bytes()).hexdigest()==expected_sha,'Checkpoint file failed integrity check: '+relative
    restore_adapter_dir=RECOVERY_CHECKPOINT_30B/'adapter'
    prior_updates=checkpoint_meta['optimizer_updates']
else:
    restore_adapter_dir=FULL_RUN_ROOT/'initial_adapter'
    # Compare the persisted initial copy with the original preflight artifact whose hash was recorded before any updates.
    original_initial=Path('/content/drive/MyDrive/SVAGA/qwen3coder30b-preflight-v1/disposable-3f354f1b83b1/initial_adapter/adapter_model.safetensors')
    assert hashlib.sha256(original_initial.read_bytes()).hexdigest()==run_plan['initial_adapter_source_sha256']
    original_values=load_file(str(original_initial),device='cpu')
    restored_values=load_file(str(restore_adapter_dir/'adapter_model.safetensors'),device='cpu')
    assert set(original_values)==set(restored_values)
    assert all(original_values[k].dtype==v.dtype and torch.equal(original_values[k],v) for k,v in restored_values.items())
    assert any('lora_B' in k for k in restored_values)
    assert all(torch.count_nonzero(v).item()==0 for k,v in restored_values.items() if 'lora_B' in k)
    del original_values,restored_values
    print('No complete training checkpoint found. Verified original untrained adapter; no pilot updates will be carried over.',flush=True)

# Upload the same frozen 24 MB dataset ZIP. Do not upload old model exports or prompt packets.
print('Select ONLY swesmith-context-repair-10k-v2.zip',flush=True)
uploaded=files.upload()
assert len(uploaded)==1
_,zip_bytes=next(iter(uploaded.items()))
assert hashlib.sha256(zip_bytes).hexdigest()=='b55b143fc41ec5dd35e1aca897168a293b83e6d83ecc698973d79318519fe3fd','Wrong or changed dataset ZIP.'
with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
    assert len(archive.namelist())==3 and set(archive.namelist())=={'manifest.json','train.jsonl','validation.jsonl'}
    manifest=json.loads(archive.read('manifest.json'));rows={}
    for split,count in (('train',10000),('validation',1000)):
        raw=archive.read(split+'.jsonl')
        expected=run_plan['input_sha256'][split+'.jsonl']
        assert hashlib.sha256(raw).hexdigest()==expected==manifest['files_sha256'][split+'.jsonl']
        rows[split]=[json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
        assert len(rows[split])==len({r['instance_id'] for r in rows[split]})==count
for key in ('instance_id','repo','bug_patch_sha256','buggy_excerpts_sha256'):
    assert not {r[key] for r in rows['train']} & {r[key] for r in rows['validation']},'Split overlap: '+key
print('Frozen dataset hashes, counts and split isolation verified.',flush=True)

adapter_config=json.loads((restore_adapter_dir/'adapter_config.json').read_text())
assert adapter_config['base_model_name_or_path']==MODEL_ID and adapter_config['revision']==REVISION
assert adapter_config['r']==16 and adapter_config['lora_alpha']==16 and adapter_config['lora_dropout']==0
assert adapter_config['bias']=='none' and set(adapter_config['target_modules'])=={'q_proj','k_proj','v_proj','o_proj'}
assert not adapter_config.get('use_dora') and not adapter_config.get('use_rslora') and not adapter_config.get('modules_to_save')
print('Loading exact pinned 30B base. A new VM may need to download weights again.',flush=True)
started=time.perf_counter()
model,tokenizer=FastModel.from_pretrained(model_name=MODEL_ID,revision=REVISION,use_exact_model_name=True,
    max_seq_length=8192,dtype=torch.bfloat16,load_in_4bit=True,full_finetuning=False,
    device_map={'':0},trust_remote_code=False)
assert getattr(model.config,'_commit_hash',None)==REVISION and getattr(model,'is_loaded_in_4bit',False)
model=FastModel.get_peft_model(model,r=16,lora_alpha=16,lora_dropout=0,bias='none',
    target_modules=['q_proj','k_proj','v_proj','o_proj'],use_gradient_checkpointing='unsloth',random_state=42)
model.peft_config['default'].revision=REVISION
saved_adapter=load_file(str(restore_adapter_dir/'adapter_model.safetensors'),device='cpu')
outcome=set_peft_model_state_dict(model,saved_adapter,adapter_name='default')
assert not outcome.unexpected_keys and not any('lora_' in k for k in outcome.missing_keys)
assert set(get_peft_model_state_dict(model))==set(saved_adapter)
assert all(v.detach().cpu().dtype==saved_adapter[k].dtype and torch.equal(v.detach().cpu(),saved_adapter[k])
    for k,v in get_peft_model_state_dict(model).items())
model.requires_grad_(False);model.eval();model.config.use_cache=False
tokenizer=getattr(tokenizer,'tokenizer',tokenizer)
assert hashlib.sha256(json.dumps(tokenizer.chat_template,sort_keys=True).encode()).hexdigest()==run_plan['chat_template_sha256']

prepared={};split_details={}
for split in ('train','validation'):
    examples=[]
    for row in rows[split]:
        assert [m['role'] for m in row['messages']]==['user','assistant']
        full=tokenizer.apply_chat_template(row['messages'],tokenize=True,add_generation_prompt=False,truncation=False,return_dict=False)
        prompt=tokenizer.apply_chat_template(row['messages'][:1],tokenize=True,add_generation_prompt=True,truncation=False,return_dict=False)
        assert isinstance(full,list) and 0<len(prompt)<len(full)<=4096 and full[:len(prompt)]==prompt
        examples.append({'task':row['instance_id'],'input_ids':full,'prompt_length':len(prompt),'target_tokens':len(full)-len(prompt)})
        if len(examples)%1000==0:print(split,len(examples),'restored',flush=True)
    prepared[split]=examples
    split_details[split]={'records':len(examples),'longest':max(len(e['input_ids']) for e in examples),
        'target_tokens':sum(e['target_tokens'] for e in examples)}
if RECOVERY_CHECKPOINT_30B is not None:
    for split,key in (('train','prepared_train_sha256'),('validation','prepared_validation_sha256')):
        h=hashlib.sha256()
        for e in prepared[split]:
            h.update(json.dumps({'task':e['task'],'input_ids':e['input_ids'],'prompt_length':e['prompt_length']},sort_keys=True,separators=(',',':')).encode());h.update(b'\n')
        assert h.hexdigest()==runtime_config[key],'Prepared inputs differ from checkpoint runtime: '+split
recovery_report={'scope':'session_restore_only_no_training_or_evaluation','model':MODEL_ID,'revision':REVISION,
    'software':software,'gpu':torch.cuda.get_device_name(0),'adapter_source':str(restore_adapter_dir),
    'checkpoint_to_resume':str(RECOVERY_CHECKPOINT_30B) if RECOVERY_CHECKPOINT_30B else None,
    'prior_completed_updates':prior_updates,'prior_training_examples_seen':prior_updates*8,
    'baseline_generations_sha256':hashlib.sha256(generation_path.read_bytes()).hexdigest(),
    'splits':split_details,'adapter_tensors_restored_exactly':True,'optimizer_updates_in_recovery':0,
    'load_and_prepare_seconds':time.perf_counter()-started}
recovery_reports=FULL_RUN_ROOT/'session-recoveries';recovery_reports.mkdir(exist_ok=True)
recovery_path=recovery_reports/('recovery-'+uuid.uuid4().hex[:12]+'.json')
with recovery_path.open('x') as stream:json.dump(recovery_report,stream,indent=2)
print(json.dumps(recovery_report,indent=2))
print('Recovery ready. Completed baselines and generations were preserved, not repeated.')
print('No training performed. Next run the UPDATED actual-training cell; it reads RECOVERY_CHECKPOINT_30B automatically.')
