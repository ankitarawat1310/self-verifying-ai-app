# SAME A100 session after the final strict loss-reload mismatch.
# Bounded diagnostic: at most four records, normal vs force-eager, two repetitions.
# Then download an evidence backup. No training or model reload.
import hashlib,json,math,shutil,time,uuid,zipfile
from pathlib import Path
from contextlib import nullcontext
import torch
from peft import get_peft_model_state_dict
from safetensors.torch import load_file
from google.colab import files

RUN30=Path('/content/drive/MyDrive/SVAGA/context-qwen3coder30b-10k-v1')
EXPORT30=RUN30/'final_export';VERIFY30=RUN30/'final_verification'
assert globals().get('model') is not None and globals().get('prepared') is not None
failed_path=VERIFY30/'reload_check.json';failed_raw=failed_path.read_bytes();failed=json.loads(failed_raw)
assert failed['match'] is False and failed['adapter_tensors_match_exactly'] and failed['serialized_frozen_base_matches']
assert getattr(model.config,'_commit_hash',None)==failed['revision']
assert not (VERIFY30/'RELOAD_MATCH').exists()
weights=load_file(str(EXPORT30/'adapter/adapter_model.safetensors'),device='cpu')

def adapter_exact30():
    live=get_peft_model_state_dict(model)
    assert set(live)==set(weights)
    assert all(v.detach().cpu().dtype==weights[k].dtype and torch.equal(v.detach().cpu(),weights[k]) for k,v in live.items())
    return True

assert adapter_exact30()
DIAG30=VERIFY30/'compiler-path-diagnostic.json'
if DIAG30.exists():
    diagnostic=json.loads(DIAG30.read_text())
    assert diagnostic['failed_report_sha256']==hashlib.sha256(failed_raw).hexdigest()
    print('Existing compiler-path diagnostic found; not repeating forward passes.')
else:
    # Select disagreements for DIAGNOSIS, not as a new performance/evaluation subset.
    ranked=sorted(failed['per_task_comparisons'],key=lambda r:(-r['absolute_difference'],r['task']))
    chosen=ranked[:3]
    controls=sorted((r for r in ranked if r['match']),key=lambda r:r['task'])
    if controls:chosen+=controls[:1]
    lookup={e['task']:e for e in prepared['validation']}
    diagnostic={'scope':'diagnostic_selected_disagreements_not_a_performance_score',
        'model':failed['model'],'revision':failed['revision'],
        'failed_report_sha256':hashlib.sha256(failed_raw).hexdigest(),
        'selection':'three largest per-task discrepancies plus first alphabetic matching control',
        'selected_tasks':[r['task'] for r in chosen],'phases':[],'optimizer_updates':0,
        'strict_original_reload_check_passed':False,
        'limitations':['force_eager disables torch.compile directives, not every custom Unsloth/Triton kernel.',
            'Agreement on these selected cases does not prove the cause or fix full-set cross-reload reproducibility.',
            'Original failed result and tolerance remain unchanged.']}
    original_mode=model.training;original_flags=[(p,p.requires_grad) for p in model.parameters()]
    original_cache=model.config.use_cache
    try:
        model.requires_grad_(False);model.eval();model.config.use_cache=False
        assert not any(m.training for m in model.modules())
        with torch.random.fork_rng(devices=[0]):
            torch.manual_seed(42);torch.cuda.manual_seed_all(42)
            for name,stance in (('normal','default'),('uncompiled','force_eager')):
                phase={'name':name,'compiler_stance':stance,'passes':[]}
                print('DIAGNOSTIC MODE:',name,flush=True)
                # Context restores the previous stance afterward. Original BF16 dtype is unchanged.
                with torch.compiler.set_stance(stance),torch.no_grad():
                    for repeat in (1,2):
                        values=[]
                        for row in chosen:
                            e=lookup[row['task']]
                            ids=torch.tensor([e['input_ids']],dtype=torch.long,device='cuda')
                            labels=ids.clone();labels[:,:e['prompt_length']]=-100
                            assert int((labels[:,1:]!=-100).sum())==e['target_tokens']
                            cpu_rng=torch.get_rng_state().clone();gpu_rng=torch.cuda.get_rng_state().clone()
                            with torch.autocast('cuda',dtype=torch.bfloat16):
                                out=model(input_ids=ids,attention_mask=torch.ones_like(ids),labels=labels,use_cache=False)
                            value=float(out.loss.float());assert math.isfinite(value)
                            item={'task':e['task'],'loss':value,
                                'difference_from_saved_pre_reload':value-row['saved_loss'],
                                'difference_from_prior_post_reload':value-row['reloaded_loss'],
                                'matches_saved_pre_reload':math.isclose(value,row['saved_loss'],rel_tol=1e-4,abs_tol=1e-5),
                                'matches_prior_post_reload':math.isclose(value,row['reloaded_loss'],rel_tol=1e-4,abs_tol=1e-5),
                                'rng_changed':not torch.equal(cpu_rng,torch.get_rng_state()) or not torch.equal(gpu_rng,torch.cuda.get_rng_state())}
                            values.append(item)
                            print(name,'pass',repeat,e['task'],'loss:',value,flush=True)
                            del ids,labels,out
                        phase['passes'].append(values)
                phase['repeat_absolute_differences']=[abs(a['loss']-b['loss']) for a,b in zip(*phase['passes'])]
                diagnostic['phases'].append(phase)
        diagnostic['adapter_tensors_unchanged']=adapter_exact30()
        assert all(p.grad is None for p in model.parameters())
    except Exception as exc:
        diagnostic['execution_error']=type(exc).__name__+': '+str(exc)
        print('Diagnostic stopped; error will be preserved in the evidence backup:',diagnostic['execution_error'],flush=True)
    finally:
        for p,flag in original_flags:p.requires_grad_(flag)
        model.train(original_mode);model.config.use_cache=original_cache
        del original_flags
    assert failed_path.read_bytes()==failed_raw
    diagnostic['failed_report_preserved']=True
    with DIAG30.open('x') as stream:json.dump(diagnostic,stream,indent=2)
print(json.dumps(diagnostic,indent=2))

# Preserve all original export bytes/hashes and add explicit current evidence/status.
archive_path=Path('/content/SVAGA_Qwen3Coder30B_10K_Training_Evidence_v1.zip')
if not archive_path.exists():
    stage=Path('/content')/('svaga-30b-evidence-'+uuid.uuid4().hex[:12]);stage.mkdir(exist_ok=False)
    for child in EXPORT30.iterdir():
        if child.is_dir():shutil.copytree(child,stage/child.name)
        else:shutil.copy2(child,stage/child.name)
    original_manifest=json.loads((EXPORT30/'export_manifest.json').read_text())
    for relative,digest in original_manifest['files_sha256'].items():
        assert hashlib.sha256((stage/relative).read_bytes()).hexdigest()==digest
    shutil.copytree(VERIFY30,stage/'verification')
    status={'scope':'trained_model_and_evidence_backup_not_a_functional_success_claim',
        'model':failed['model'],'revision':failed['revision'],'training_records':10000,'optimizer_updates':1250,
        'artifact_restore_identity':{'adapter_tensors':'exact_match','tokenizer_inputs':'exact_match','serialized_frozen_base':'exact_match'},
        'strict_loss_reproducibility':'FAILED_original_result_preserved',
        'dev100_before':0.6829081848793719,'dev100_after_at_export':0.22452987680875175,
        'dev100_after_reloaded':failed['reloaded_validation_loss'],
        'original_reduction_percent':67.12151328975324,
        'full_dev1000_paired_evaluation':'pending','trained_executable_repairs':'pending','external_benchmark':'not_run',
        'retraining_required_by_this_check':False,'cause_of_numerical_difference':'not_established',
        'note':'Original results.json/export_manifest.json describe the initial export; this STATUS file and verification reports add later evidence without overwriting them.'}
    (stage/'STATUS.json').write_text(json.dumps(status,indent=2))
    (stage/'EVIDENCE_README.md').write_text('# Training evidence backup\n\n'
        'Training completed on 10,000 records. Exported adapter tensors, tokenizer inputs and serialized frozen base matched exactly on restoration.\n\n'
        'The strict loss reproduction check FAILED and is preserved under verification/. Its cause is not established. Do not describe it as a passing numerical reproducibility test.\n\n'
        'Prediction loss is not functional repair accuracy or application security. Full development-set and executable evaluations remain pending.\n\n'
        'The ZIP contains the LoRA adapter and tokenizer, not the full 30B base or optimizer states. Resume checkpoints remain on Drive.\n')
    hashes={str(p.relative_to(stage)):hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob('*') if p.is_file()}
    (stage/'evidence_manifest.json').write_text(json.dumps({'files_sha256':hashes,'original_export_preserved':True},indent=2))
    shutil.make_archive(str(archive_path.with_suffix('')),'zip',stage)
with zipfile.ZipFile(archive_path) as archive:
    evidence_manifest=json.loads(archive.read('evidence_manifest.json'))
    for relative,digest in evidence_manifest['files_sha256'].items():
        assert hashlib.sha256(archive.read(relative)).hexdigest()==digest,'Backup hash mismatch: '+relative
print('Backup ZIP:',archive_path)
print('Backup SHA256:',hashlib.sha256(archive_path.read_bytes()).hexdigest())
print('Original failed report retained. No training and no model reload performed.')
files.download(str(archive_path))
