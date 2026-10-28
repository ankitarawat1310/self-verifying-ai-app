# SAME A100 Colab session after all 20 BASE generations have been saved.
# Starts the ACTUAL one-epoch 10K run; pauses after update 10 for a measured ETA.
# Continue later with train_30b_segment(1250); the first 80 records are not repeated.
import gc, hashlib, json, math, random, re, time, uuid
from pathlib import Path
from importlib.metadata import version
import numpy as np
from unsloth import FastModel
import torch
from peft import get_peft_model_state_dict, set_peft_model_state_dict
from safetensors.torch import load_file

RESUME_FROM_30B = globals().get('RECOVERY_CHECKPOINT_30B', None)  # Set only by the hash-verified recovery cell, or None for the original fresh run.
RUNTIME_ID_30B = 'qwen3coder30b-context10k-bf16-adamw-v1'
FULL_RUN_ROOT=Path('/content/drive/MyDrive/SVAGA/context-qwen3coder30b-10k-v1')
assert globals().get('model') is not None and globals().get('prepared') is not None
assert 'training_state_30b' not in globals(), 'Runtime already initialized. Use train_30b_segment(...) instead of rerunning this cell.'
assert getattr(model.config,'_commit_hash',None)=='b2cff646eb4bb1d68355c01b18ae02e7cf42d120'
assert len(prepared['train'])==10000 and len(prepared['validation'])==1000
assert not {e['task'] for e in prepared['train']} & {e['task'] for e in prepared['validation']}
assert all(0<e['prompt_length']<len(e['input_ids'])<=4096 for split in prepared.values() for e in split)
assert all(e['target_tokens']==len(e['input_ids'])-e['prompt_length'] for split in prepared.values() for e in split)
assert (FULL_RUN_ROOT/'BASELINE_COMPLETE').exists()
assert (FULL_RUN_ROOT/'dev20-base/GENERATION_COMPLETE').exists()
GEN_FILE_30B=FULL_RUN_ROOT/'dev20-base/qwen3coder30b_dev20_base_generations.json'
base_generations=json.loads(GEN_FILE_30B.read_text())
assert base_generations['model']==MODEL_ID and base_generations['revision']==REVISION
assert base_generations['adapter_mode']=='disabled' and len(base_generations['records'])==20
assert len({r['instance_id'] for r in base_generations['records']})==20
assert all(r['variant']=='base' for r in base_generations['records'])
run_plan=json.loads((FULL_RUN_ROOT/'config.json').read_text())
actual_software={p:version(p) for p in ('torch','transformers','peft','accelerate','bitsandbytes','unsloth','unsloth_zoo')}
assert actual_software==run_plan['software'],'Software changed; stop and record a new experiment.'
assert all(getattr(m,'max_seq_length',8192)>=8192 for m in model.modules() if isinstance(getattr(m,'max_seq_length',None),int))
existing_checkpoints=sorted(p for p in FULL_RUN_ROOT.glob('step-*') if p.is_dir())
if RESUME_FROM_30B is None:
    assert not existing_checkpoints, 'Checkpoints exist. Set RESUME_FROM_30B to a verified COMPLETE checkpoint; never restart from zero here.'
else:
    RESUME_FROM_30B=Path(RESUME_FROM_30B)
    assert RESUME_FROM_30B.resolve().parent==FULL_RUN_ROOT.resolve()
    assert re.fullmatch(r'step-\d{5}',RESUME_FROM_30B.name)


def sha30(raw):return hashlib.sha256(raw).hexdigest()


def prepared_digest30(split):
    digest=hashlib.sha256()
    for e in prepared[split]:
        digest.update(json.dumps({'task':e['task'],'input_ids':e['input_ids'],'prompt_length':e['prompt_length']},sort_keys=True,separators=(',',':')).encode())
        digest.update(b'\n')
    return digest.hexdigest()


def batch30(example):
    ids=torch.tensor([example['input_ids']],dtype=torch.long,device='cuda')
    labels=ids.clone();labels[:,:example['prompt_length']]=-100
    assert int((labels[:,1:]!=-100).sum())==example['target_tokens']>0
    return {'input_ids':ids,'attention_mask':torch.ones_like(ids),'labels':labels}


def eval30(examples,disable_adapter=False):
    from contextlib import nullcontext
    was_training=model.training
    flags=[(p,p.requires_grad) for p in model.parameters()]
    model.requires_grad_(False);model.eval();model.config.use_cache=False
    total=0.;targets=0;details=[]
    try:
        with (model.disable_adapter() if disable_adapter else nullcontext()),torch.no_grad():
            for number,e in enumerate(examples,1):
                batch=batch30(e)
                with torch.autocast('cuda',dtype=torch.bfloat16):out=model(**batch,use_cache=False)
                loss=float(out.loss.float());assert math.isfinite(loss)
                count=e['target_tokens'];total+=loss*count;targets+=count
                details.append({'task':e['task'],'loss':loss,'target_tokens':count})
                if number%10==0:print('Runtime baseline:',number,'/',len(examples),flush=True)
                del batch,out
    finally:
        for parameter,flag in flags:parameter.requires_grad_(flag)
        model.train(was_training)
    return {'scope':'development_subset_prediction_loss','examples':len(examples),'target_tokens':targets,
            'token_weighted_loss':total/targets,'details':details,'adapter_mode':'disabled' if disable_adapter else 'active',
            'model_context_length':8192,'optimizer_updates':0}


# Restore a fresh initial adapter or a checkpoint adapter; generation outputs stay untouched.
initial_path=FULL_RUN_ROOT/'initial_adapter/adapter_model.safetensors'
if RESUME_FROM_30B is None:
    initial=load_file(str(initial_path),device='cpu')
    live=get_peft_model_state_dict(model)
    assert set(initial)==set(live) and all(torch.equal(v.detach().cpu(),initial[k]) for k,v in live.items()),'Current adapter is not the original untrained state.'
    assert any('lora_B' in k for k in initial)
    assert all(torch.count_nonzero(v).item()==0 for k,v in initial.items() if 'lora_B' in k)
    del initial,live
model.set_adapter('default')
FastModel.for_training(model,use_gradient_checkpointing='unsloth')
model.requires_grad_(False)
for name,parameter in model.named_parameters():
    if 'lora_' in name:parameter.requires_grad_(True)
model.config.use_cache=False
trainable_names30=[name for name,p in model.named_parameters() if p.requires_grad]
assert trainable_names30 and all('lora_' in name for name in trainable_names30)
assert sum(p.numel() for p in model.parameters() if p.requires_grad)==13369344
runtime_config30={'runtime_id':RUNTIME_ID_30B,'model':MODEL_ID,'revision':REVISION,'software':actual_software,
    'dataset_sha256':run_plan['input_sha256'],'prepared_train_sha256':prepared_digest30('train'),
    'prepared_validation_sha256':prepared_digest30('validation'),
    'baseline_generations_sha256':sha30(GEN_FILE_30B.read_bytes()),'initial_adapter_sha256':sha30(initial_path.read_bytes()),
    'seed':42,'epochs':1,'train_records':10000,'validation_records':1000,'updates':1250,
    'accumulation':8,'microbatch':1,'learning_rate':2e-5,'weight_decay':0.,'gradient_clip':1.,
    'model_context_length':8192,'max_training_example_tokens':4096,'dtype':'bfloat16',
    'lora':run_plan['planned_training']['lora'],'trainable_parameter_names':trainable_names30,
    'objective':'mean of per-example mean target-token losses within each group of eight',
    'checkpoint_policy':'step 0, step 1, every 50 updates, segment end, and final; retain complete checkpoints'}
config_fingerprint30=sha30(json.dumps(runtime_config30,sort_keys=True).encode())
config_path30=FULL_RUN_ROOT/'training-runtime-config.json'
if config_path30.exists():assert json.loads(config_path30.read_text())==runtime_config30,'Existing runtime configuration differs.'
else:config_path30.write_text(json.dumps(runtime_config30,indent=2))


def validate_checkpoint30(folder):
    folder=Path(folder)
    assert folder.resolve().parent==FULL_RUN_ROOT.resolve() and re.fullmatch(r'step-\d{5}',folder.name)
    assert (folder/'COMPLETE').exists(),'Checkpoint incomplete.'
    metadata=json.loads((folder/'checkpoint_manifest.json').read_text())
    assert metadata['runtime_fingerprint']==config_fingerprint30
    assert metadata['optimizer_updates']==int(folder.name.split('-')[1])
    assert metadata['next_position']==8*metadata['optimizer_updates']
    assert {'training_state.pt','adapter/adapter_model.safetensors','adapter/adapter_config.json'}<=set(metadata['files_sha256'])
    for relative,digest in metadata['files_sha256'].items():
        rel=Path(relative);assert not rel.is_absolute() and '..' not in rel.parts
        assert sha30((folder/rel).read_bytes())==digest,'Checkpoint file hash mismatch: '+relative
    return metadata


optimizer30=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=2e-5,weight_decay=0.)
if RESUME_FROM_30B is None:
    random.seed(42);np.random.seed(42);torch.manual_seed(42);torch.cuda.manual_seed_all(42)
    comparison_validation=sorted(prepared['validation'],key=lambda e:sha30(e['task'].encode()))[:100]
    expected_ids=json.loads((FULL_RUN_ROOT/'baseline-validation-ids.json').read_text())
    assert [e['task'] for e in comparison_validation]==expected_ids
    # Record the actual 8K-context runtime baseline separately; preserve the earlier 4K result.
    baseline_path30=FULL_RUN_ROOT/'baseline-runtime8192.json'
    if baseline_path30.exists():
        baseline_runtime30=json.loads(baseline_path30.read_text())
        assert baseline_runtime30['runtime_fingerprint']==config_fingerprint30
    else:
        print('Recording the pre-training base loss in the actual 8K-context runtime...',flush=True)
        baseline_runtime30=eval30(comparison_validation,disable_adapter=True)
        baseline_runtime30['runtime_fingerprint']=config_fingerprint30
        baseline_runtime30['prior_context4096_loss']=json.loads((FULL_RUN_ROOT/'baseline.json').read_text())['token_weighted_loss']
        baseline_path30.write_text(json.dumps(baseline_runtime30,indent=2))
    print('Training-runtime base loss:',baseline_runtime30['token_weighted_loss'],flush=True)
    order=list(range(10000));random.Random(42).shuffle(order)
    training_state_30b={'next_position':0,'optimizer_updates':0,'order':order,'log':[],'peak_allocated_gpu_gib':0.,
        'phase':'ready','baseline_loss':baseline_runtime30['token_weighted_loss']}
else:
    metadata=validate_checkpoint30(RESUME_FROM_30B)
    saved=load_file(str(RESUME_FROM_30B/'adapter/adapter_model.safetensors'),device='cpu')
    outcome=set_peft_model_state_dict(model,saved,adapter_name='default')
    assert not outcome.unexpected_keys and not any('lora_' in k for k in outcome.missing_keys)
    assert set(get_peft_model_state_dict(model))==set(saved)
    assert all(torch.equal(v.detach().cpu(),saved[k]) for k,v in get_peft_model_state_dict(model).items())
    # Only our own hash-verified checkpoint in this run folder is unpickled.
    owned=torch.load(RESUME_FROM_30B/'training_state.pt',map_location='cpu',weights_only=False)
    assert owned['runtime_fingerprint']==config_fingerprint30
    training_state_30b=owned['run'];optimizer30.load_state_dict(owned['optimizer'])
    assert training_state_30b['optimizer_updates']==metadata['optimizer_updates']
    assert training_state_30b['next_position']==metadata['next_position']
    random.setstate(owned['python_rng']);np.random.set_state(owned['numpy_rng'])
    torch.set_rng_state(owned['torch_rng']);torch.cuda.set_rng_state_all(owned['cuda_rng'])
    training_state_30b['phase']='ready'
    del owned,saved
assert sorted(training_state_30b['order'])==list(range(10000))
assert training_state_30b['next_position']==8*training_state_30b['optimizer_updates']


def progress30():
    s=training_state_30b
    value={'runtime_fingerprint':config_fingerprint30,'phase':s['phase'],'examples_seen':s['next_position'],
        'optimizer_updates':s['optimizer_updates'],'total_records':10000,'total_updates':1250,
        'full_training_started':s['optimizer_updates']>0,'peak_allocated_gpu_gib':s['peak_allocated_gpu_gib']}
    temp=FULL_RUN_ROOT/'training-progress.tmp';temp.write_text(json.dumps(value,indent=2));temp.replace(FULL_RUN_ROOT/'training-progress.json')


def save_checkpoint30():
    s=training_state_30b;step=s['optimizer_updates'];destination=FULL_RUN_ROOT/f'step-{step:05d}'
    if destination.exists():
        metadata=validate_checkpoint30(destination)
        assert metadata['next_position']==s['next_position']
        return destination
    stage=FULL_RUN_ROOT/f'.incomplete-step-{step:05d}-{uuid.uuid4().hex}'
    stage.mkdir(exist_ok=False)
    model.peft_config['default'].revision=REVISION
    model.save_pretrained(stage/'adapter',safe_serialization=True);tokenizer.save_pretrained(stage/'tokenizer')
    torch.save({'runtime_fingerprint':config_fingerprint30,'run':dict(s),'optimizer':optimizer30.state_dict(),
        'python_rng':random.getstate(),'numpy_rng':np.random.get_state(),'torch_rng':torch.get_rng_state(),
        'cuda_rng':torch.cuda.get_rng_state_all()},stage/'training_state.pt')
    hashes={str(p.relative_to(stage)):sha30(p.read_bytes()) for p in stage.rglob('*') if p.is_file()}
    metadata={'runtime_fingerprint':config_fingerprint30,'optimizer_updates':step,'next_position':s['next_position'],
        'files_sha256':hashes}
    (stage/'checkpoint_manifest.json').write_text(json.dumps(metadata,indent=2))
    (stage/'COMPLETE').write_text('Owned adapter, optimizer and RNG state saved; file hashes recorded.\n')
    stage.rename(destination)
    (FULL_RUN_ROOT/'latest_checkpoint.txt').write_text(str(destination))
    print('Checkpoint:',destination,flush=True)
    return destination


def train_30b_segment(stop_at_update=1250):
    s=training_state_30b
    assert s['phase']=='ready','Previous segment failed or is active. Restore a complete checkpoint before continuing.'
    assert s['optimizer_updates']<=stop_at_update<=1250
    assert s['next_position']==8*s['optimizer_updates']
    if s['optimizer_updates']==stop_at_update:
        print('Already at requested update:',stop_at_update);return
    FastModel.for_training(model,use_gradient_checkpointing='unsloth')
    model.requires_grad_(False)
    for name,parameter in model.named_parameters():
        if 'lora_' in name:parameter.requires_grad_(True)
    assert [name for name,p in model.named_parameters() if p.requires_grad]==trainable_names30
    model.config.use_cache=False;model.train();optimizer30.zero_grad(set_to_none=True)
    gc.collect();torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats()
    started=time.perf_counter();start_position=s['next_position'];s['phase']='running';progress30()
    try:
        while s['optimizer_updates']<stop_at_update:
            group_loss=0.;tasks=[];group_started=time.perf_counter()
            for offset in range(8):
                e=prepared['train'][s['order'][s['next_position']+offset]]
                batch=batch30(e)
                with torch.autocast('cuda',dtype=torch.bfloat16):out=model(**batch,use_cache=False);loss=out.loss
                assert torch.isfinite(loss).item(),'Nonfinite loss.'
                group_loss+=float(loss.detach().float());tasks.append(e['task'])
                (loss/8).backward()
                del batch,out,loss
            params=[p for p in model.parameters() if p.requires_grad]
            norm=torch.nn.utils.clip_grad_norm_(params,1.,error_if_nonfinite=True)
            assert math.isfinite(float(norm))
            assert all(p.grad is None for p in model.parameters() if not p.requires_grad),'Frozen-weight gradient detected.'
            optimizer30.step();optimizer30.zero_grad(set_to_none=True)
            assert all(torch.isfinite(p).all().item() for p in params),'Nonfinite adapter weights.'
            del params
            torch.cuda.synchronize()
            s['next_position']+=8;s['optimizer_updates']+=1
            s['peak_allocated_gpu_gib']=max(s['peak_allocated_gpu_gib'],torch.cuda.max_memory_allocated()/2**30)
            s['log'].append({'update':s['optimizer_updates'],'examples_seen':s['next_position'],
                'mean_example_loss':group_loss/8,'gradient_norm':float(norm),'tasks':tasks,
                'seconds':time.perf_counter()-group_started})
            progress30()
            elapsed=time.perf_counter()-started;seen=s['next_position']-start_position
            eta=elapsed/seen*(10000-s['next_position'])/60
            if s['optimizer_updates']<=10 or s['optimizer_updates']%10==0:
                print(f"Update {s['optimizer_updates']}/1250 | examples {s['next_position']}/10000 | loss {group_loss/8:.4f} | remaining ~{eta:.1f} min",flush=True)
            if s['optimizer_updates']==1 or s['optimizer_updates']%50==0 or s['optimizer_updates']==stop_at_update:
                save_checkpoint30()
        s['phase']='ready';progress30()
        if s['next_position']==10000:
            (FULL_RUN_ROOT/'TRAINING_COMPLETE').write_text('One epoch: 10,000 training records, 1,250 optimizer updates. Post-training evaluation pending.\n')
            print('Full 10K epoch complete. Next: evaluation and final saved-adapter verification.')
        else:
            print('Segment complete:',s['next_position'],'/10000 examples; checkpoint saved.')
            print('Continue the same epoch with: train_30b_segment(1250)')
        print('Peak allocated GPU GiB:',round(s['peak_allocated_gpu_gib'],2))
    except BaseException as exc:
        s['phase']='needs_checkpoint_restore';optimizer30.zero_grad(set_to_none=True);progress30()
        error={'error':type(exc).__name__+': '+str(exc),'last_committed_update':s['optimizer_updates'],
            'last_complete_checkpoint':(FULL_RUN_ROOT/'latest_checkpoint.txt').read_text() if (FULL_RUN_ROOT/'latest_checkpoint.txt').exists() else None,
            'instruction':'Preserve checkpoints. Restore a verified complete checkpoint; do not rerun from zero or continue a partially failed optimizer.'}
        (FULL_RUN_ROOT/('interruption-'+uuid.uuid4().hex[:12]+'.json')).write_text(json.dumps(error,indent=2))
        raise

if RESUME_FROM_30B is None:
    # Step 0 is a durable recovery point before the first actual optimizer update.
    checkpoint0=save_checkpoint30()
    validate_checkpoint30(checkpoint0)
else:print('Resumed at:',training_state_30b['next_position'],'examples',flush=True)
progress30()
print('Starting/continuing the actual 10K epoch. First segment ends at update 10 (80 examples).',flush=True)
train_30b_segment(max(10,training_state_30b['optimizer_updates']))
