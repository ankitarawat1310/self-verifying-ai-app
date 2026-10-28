# SAME A100 Colab session after the completed 10,000-record / 1,250-update epoch.
# Evaluates the trained adapter on the fixed 100 dev records and exports adapter-only artifacts.
import hashlib,json,math,shutil,time,uuid
from pathlib import Path
import torch
from peft import get_peft_model_state_dict
from safetensors.torch import load_file

FULL_RUN_ROOT=Path('/content/drive/MyDrive/SVAGA/context-qwen3coder30b-10k-v1')
assert globals().get('model') is not None and globals().get('prepared') is not None
assert training_state_30b['next_position']==10000 and training_state_30b['optimizer_updates']==1250
assert training_state_30b['phase']=='ready'
assert (FULL_RUN_ROOT/'TRAINING_COMPLETE').exists()
assert getattr(model.config,'_commit_hash',None)==REVISION
FINAL_CKPT_30B=FULL_RUN_ROOT/'step-01250'
final_metadata=validate_checkpoint30(FINAL_CKPT_30B)
assert final_metadata['next_position']==10000 and final_metadata['optimizer_updates']==1250
FINAL_EXPORT_30B=FULL_RUN_ROOT/'final_export'
assert not FINAL_EXPORT_30B.exists(),'Final export already exists. Read its results; do not overwrite or rerun.'
# Confirm the live trained adapter is exactly the final saved checkpoint.
checkpoint_weights=load_file(str(FINAL_CKPT_30B/'adapter/adapter_model.safetensors'),device='cpu')
live=get_peft_model_state_dict(model)
assert set(live)==set(checkpoint_weights)
assert all(v.detach().cpu().dtype==checkpoint_weights[k].dtype and torch.equal(v.detach().cpu(),checkpoint_weights[k]) for k,v in live.items())
del live
baseline30=json.loads((FULL_RUN_ROOT/'baseline-runtime8192.json').read_text())
assert baseline30['runtime_fingerprint']==config_fingerprint30
assert baseline30['adapter_mode']=='disabled' and baseline30['examples']==100
comparison_validation=sorted(prepared['validation'],key=lambda e:hashlib.sha256(e['task'].encode()).hexdigest())[:100]
assert [e['task'] for e in comparison_validation]==json.loads((FULL_RUN_ROOT/'baseline-validation-ids.json').read_text())
assert [e['task'] for e in comparison_validation]==[d['task'] for d in baseline30['details']]
assert not {e['task'] for e in comparison_validation}&{e['task'] for e in prepared['train']}
print('Final checkpoint integrity and live adapter weights verified.',flush=True)
print('Evaluating TRAINED adapter on the same 100 development records...',flush=True)
model.set_adapter('default');model.requires_grad_(False);model.eval();model.config.use_cache=False
total=0.;target_count=0;details=[];started=time.perf_counter()
with torch.no_grad():
    for number,e in enumerate(comparison_validation,1):
        batch=batch30(e)
        with torch.autocast('cuda',dtype=torch.bfloat16):output=model(**batch,use_cache=False)
        value=float(output.loss.float());assert math.isfinite(value)
        count=e['target_tokens'];total+=value*count;target_count+=count
        details.append({'task':e['task'],'loss':value,'target_tokens':count})
        if number%10==0:print('Trained development evaluation:',number,'/ 100',flush=True)
        del batch,output
assert target_count==baseline30['target_tokens']
after_30b={'scope':'trained_adapter_development_subset_prediction_loss','examples':100,'target_tokens':target_count,
    'token_weighted_loss':total/target_count,'details':details,'adapter_mode':'active','model_context_length':8192,
    'optimizer_updates_during_evaluation':0,'seconds':time.perf_counter()-started}
before_loss=baseline30['token_weighted_loss'];after_loss=after_30b['token_weighted_loss']
assert before_loss>0
results_30b={'scope':'completed_10k_training_and_100_record_development_loss',
    'model':MODEL_ID,'revision':REVISION,'software':runtime_config30['software'],
    'gpu':torch.cuda.get_device_name(0),'training_examples':10000,'validation_available':1000,
    'comparison_validation_examples':100,'optimizer_updates':1250,'epochs':1,
    'model_context_length':8192,'max_training_example_tokens':4096,
    'lora':runtime_config30['lora'],'learning_rate':runtime_config30['learning_rate'],
    'gradient_accumulation':8,'seed':42,'training_peak_gpu_gib':training_state_30b['peak_allocated_gpu_gib'],
    'input_sha256':runtime_config30['dataset_sha256'],
    'runtime_fingerprint':config_fingerprint30,'data_status':run_plan['data_status'],
    'baseline':baseline30,'after':after_30b,'loss_change':after_loss-before_loss,
    'relative_loss_reduction_percent':(before_loss-after_loss)/before_loss*100,
    'source_checkpoint':'step-01250',
    'source_checkpoint_manifest_sha256':hashlib.sha256((FINAL_CKPT_30B/'checkpoint_manifest.json').read_bytes()).hexdigest(),
    'live_adapter_matches_final_checkpoint':True,'fresh_final_adapter_reload_check':'pending',
    'full_1000_record_comparison':'pending','trained_dev20_generation_and_executable_comparison':'pending',
    'external_terminal_bench_evaluation':'not_run',
    'limitations':['Development teacher-forced prediction loss is not executed repair accuracy or application security.',
        'Experimental localized-repair targets and supplied file locations; not a verified complete-application training corpus.',
        'The canonical before/after comparison uses the same 8K runtime, 100 task IDs and target-token weighting.',
        'The earlier 4K-context baseline and original failed pilot reload are preserved separately.',
        'Base/adapter executable results and external benchmarks remain separate pending work.']}
# Build a new export from the exact already-hashed final checkpoint artifacts.
stage=FULL_RUN_ROOT/('.incomplete-final-export-'+uuid.uuid4().hex)
stage.mkdir(exist_ok=False)
shutil.copytree(FINAL_CKPT_30B/'adapter',stage/'adapter')
shutil.copytree(FINAL_CKPT_30B/'tokenizer',stage/'tokenizer')
for relative,digest in final_metadata['files_sha256'].items():
    if relative.startswith(('adapter/','tokenizer/')):
        assert hashlib.sha256((stage/relative).read_bytes()).hexdigest()==digest
(stage/'results.json').write_text(json.dumps(results_30b,indent=2))
(stage/'dataset_manifest.json').write_bytes((FULL_RUN_ROOT/'dataset_manifest.json').read_bytes())
(stage/'training-runtime-config.json').write_bytes((FULL_RUN_ROOT/'training-runtime-config.json').read_bytes())
(stage/'baseline-validation-ids.json').write_bytes((FULL_RUN_ROOT/'baseline-validation-ids.json').read_bytes())
(stage/'training_log.json').write_text(json.dumps(training_state_30b['log'],indent=2))
(stage/'README.md').write_text(
    '# Qwen3-Coder-30B SVAGA 10K adapter\n\n'
    'This export contains LoRA adapter weights and tokenizer artifacts, not the full 30B base model.\n'
    'Required base: '+MODEL_ID+' at revision '+REVISION+'.\n\n'
    'One epoch: 10,000 training examples / 1,250 optimizer updates. '
    'results.json reports teacher-forced loss on 100 development examples, not functional repair success.\n'
    'Fresh final-adapter reload, full 1,000-record loss comparison, executable development repairs and external benchmark results remain pending at export time.\n')
export_hashes={str(p.relative_to(stage)):hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob('*') if p.is_file()}
(stage/'export_manifest.json').write_text(json.dumps({'model':MODEL_ID,'revision':REVISION,'files_sha256':export_hashes,
    'source_checkpoint':'step-01250','export_scope':'adapter_and_tokenizer_no_optimizer_or_base_weights'},indent=2))
(stage/'EXPORT_COMPLETE').write_text('Final checkpoint artifacts copied and hash-checked; 100-record development loss saved. Reload validation pending.\n')
stage.rename(FINAL_EXPORT_30B)
print('Before:',before_loss)
print('After:',after_loss)
print('Relative loss reduction (%):',results_30b['relative_loss_reduction_percent'])
print('Saved export:',FINAL_EXPORT_30B)
print('Evaluation and export completed. Zero additional optimizer updates.')
print('Next: saved final-adapter reload check; keep this Colab session available.')
