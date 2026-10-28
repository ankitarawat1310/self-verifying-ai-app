# SAME A100 Colab session after completed dev100 evaluation and final_export.
# Fresh base + EXPORTED adapter/tokenizer reload; no optimizer updates.
import gc,hashlib,json,math,time
from pathlib import Path
import torch
from unsloth import FastModel
from transformers import AutoTokenizer
from peft import get_peft_model_state_dict,set_peft_model_state_dict
from safetensors.torch import load_file

FULL_RUN_ROOT=Path('/content/drive/MyDrive/SVAGA/context-qwen3coder30b-10k-v1')
EXPORT30=FULL_RUN_ROOT/'final_export'
FINAL_VERIFY30=FULL_RUN_ROOT/'final_verification'


def final_base_fingerprint30(current_model,label):
    state=current_model.state_dict();details={};total=0
    names=sorted(k for k in state if 'lora_' not in k)
    print('Fingerprinting',label,'frozen base:',len(names),'tensors',flush=True)
    for number,name in enumerate(names,1):
        tensor=state[name].detach();flat=tensor.reshape(-1);h=hashlib.sha256()
        chunk=max(1,(16*2**20)//max(1,tensor.element_size()))
        for start in range(0,flat.numel(),chunk):
            h.update(memoryview(flat[start:start+chunk].contiguous().view(torch.uint8).cpu().numpy()))
        details[name]={'dtype':str(tensor.dtype),'shape':list(tensor.shape),'sha256':h.hexdigest()}
        total+=tensor.numel()*tensor.element_size()
        if number%1000==0:print(label,number,'/',len(names),'hashed',flush=True)
    value={'state_sha256':hashlib.sha256(json.dumps(details,sort_keys=True).encode()).hexdigest(),
        'serialized_bytes':total,'tensors':details}
    with (FINAL_VERIFY30/(label+'-base-fingerprint.json')).open('x') as stream:json.dump(value,stream,indent=2)
    return value


def final_reload_eval30(current_model,examples):
    current_model.requires_grad_(False);current_model.eval();current_model.config.use_cache=False
    assert not any(module.training for module in current_model.modules())
    total=0.;targets=0;details=[]
    with torch.no_grad():
        for number,e in enumerate(examples,1):
            ids=torch.tensor([e['input_ids']],dtype=torch.long,device='cuda')
            labels=ids.clone();labels[:,:e['prompt_length']]=-100
            count=int((labels[:,1:]!=-100).sum());assert count==e['target_tokens']>0
            with torch.autocast('cuda',dtype=torch.bfloat16):
                out=current_model(input_ids=ids,attention_mask=torch.ones_like(ids),labels=labels,use_cache=False)
            loss=float(out.loss.float());assert math.isfinite(loss)
            total+=loss*count;targets+=count
            details.append({'task':e['task'],'loss':loss,'target_tokens':count})
            if number%10==0:print('Reloaded development evaluation:',number,'/ 100',flush=True)
            del ids,labels,out
    return {'token_weighted_loss':total/targets,'target_tokens':targets,'examples':len(examples),'details':details}


def check_final_reload30():
    global model,tokenizer
    report_path=FINAL_VERIFY30/'reload_check.json'
    if report_path.exists():
        existing=json.loads(report_path.read_text())
        print('Existing final-reload result; no work repeated:')
        print(json.dumps({k:v for k,v in existing.items() if k!='per_task_comparisons'},indent=2))
        return existing
    assert globals().get('model') is not None and globals().get('prepared') is not None
    assert (FULL_RUN_ROOT/'TRAINING_COMPLETE').exists() and (EXPORT30/'EXPORT_COMPLETE').exists()
    assert getattr(model.config,'_commit_hash',None)=='b2cff646eb4bb1d68355c01b18ae02e7cf42d120'
    assert not (FINAL_VERIFY30/'before-base-fingerprint.json').exists(),'A partial verification already exists. Preserve it and share the error before retrying.'
    FINAL_VERIFY30.mkdir(exist_ok=True)
    manifest_export=json.loads((EXPORT30/'export_manifest.json').read_text())
    for relative,expected in manifest_export['files_sha256'].items():
        rel=Path(relative);assert not rel.is_absolute() and '..' not in rel.parts
        assert hashlib.sha256((EXPORT30/rel).read_bytes()).hexdigest()==expected,'Export file hash mismatch: '+relative
    results=json.loads((EXPORT30/'results.json').read_text())
    assert results['training_examples']==10000 and results['optimizer_updates']==1250
    assert results['model']==MODEL_ID and results['revision']==REVISION
    baseline_after=results['after']
    saved_weights=load_file(str(EXPORT30/'adapter/adapter_model.safetensors'),device='cpu')
    live=get_peft_model_state_dict(model)
    assert set(live)==set(saved_weights)
    assert all(v.detach().cpu().dtype==saved_weights[k].dtype and torch.equal(v.detach().cpu(),saved_weights[k]) for k,v in live.items())
    del live
    examples=sorted(prepared['validation'],key=lambda e:hashlib.sha256(e['task'].encode()).hexdigest())[:100]
    assert [e['task'] for e in examples]==[e['task'] for e in baseline_after['details']]
    assert sum(e['target_tokens'] for e in examples)==baseline_after['target_tokens']
    config=json.loads((EXPORT30/'adapter/adapter_config.json').read_text())
    assert config['base_model_name_or_path']==MODEL_ID and config['revision']==REVISION
    assert config['r']==16 and config['lora_alpha']==16 and config['lora_dropout']==0 and config['bias']=='none'
    assert set(config['target_modules'])=={'q_proj','k_proj','v_proj','o_proj'}
    assert not config.get('modules_to_save') and not config.get('use_dora') and not config.get('use_rslora')
    model.requires_grad_(False);model.eval();model.config.use_cache=False
    before_base=final_base_fingerprint30(model,'before')
    (FINAL_VERIFY30/'reference.json').write_text(json.dumps({'model':MODEL_ID,'revision':REVISION,
        'source_export_manifest_sha256':hashlib.sha256((EXPORT30/'export_manifest.json').read_bytes()).hexdigest(),
        'reference_trained_loss':baseline_after['token_weighted_loss'],
        'reference_task_ids':[e['task'] for e in examples],
        'before_base_sha256':before_base['state_sha256']},indent=2))
    # The final optimizer is safely on Drive; release its GPU tensors and old model aliases.
    for name in ('model','optimizer30','trainable','trainable_named','parameter','params'):
        globals().pop(name,None)
    torch.compiler.reset();gc.collect();torch.cuda.empty_cache()
    allocated=torch.cuda.memory_allocated()/2**30
    print('GPU allocated after releasing old model (GiB):',round(allocated,3),flush=True)
    assert allocated<4,'Old model storage remains referenced. Stop before loading a second base.'
    print('Reloading pinned base from cache and the EXPORTED adapter...',flush=True)
    started=time.perf_counter()
    model,_native=FastModel.from_pretrained(model_name=MODEL_ID,revision=REVISION,use_exact_model_name=True,
        max_seq_length=8192,dtype=torch.bfloat16,load_in_4bit=True,full_finetuning=False,
        device_map={'':0},trust_remote_code=False,local_files_only=True)
    assert getattr(model.config,'_commit_hash',None)==REVISION and getattr(model,'is_loaded_in_4bit',False)
    model=FastModel.get_peft_model(model,r=16,lora_alpha=16,lora_dropout=0,bias='none',
        target_modules=['q_proj','k_proj','v_proj','o_proj'],use_gradient_checkpointing='unsloth',random_state=42)
    model.peft_config['default'].revision=REVISION
    outcome=set_peft_model_state_dict(model,saved_weights,adapter_name='default')
    assert not outcome.unexpected_keys and not any('lora_' in k for k in outcome.missing_keys)
    assert set(get_peft_model_state_dict(model))==set(saved_weights)
    assert all(v.detach().cpu().dtype==saved_weights[k].dtype and torch.equal(v.detach().cpu(),saved_weights[k])
        for k,v in get_peft_model_state_dict(model).items())
    model.requires_grad_(False);model.eval();model.config.use_cache=False
    tokenizer=AutoTokenizer.from_pretrained(str(EXPORT30/'tokenizer'),local_files_only=True,trust_remote_code=False)
    source_by_id={r['instance_id']:r for r in rows['validation']}
    for e in examples:
        messages=source_by_id[e['task']]['messages']
        full=tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=False,truncation=False,return_dict=False)
        prompt=tokenizer.apply_chat_template(messages[:1],tokenize=True,add_generation_prompt=True,truncation=False,return_dict=False)
        assert full==e['input_ids'] and len(prompt)==e['prompt_length'] and full[:len(prompt)]==prompt
    reloaded=final_reload_eval30(model,examples)
    after_base=final_base_fingerprint30(model,'reloaded')
    changed=[key for key in set(before_base['tensors'])|set(after_base['tensors'])
        if before_base['tensors'].get(key)!=after_base['tensors'].get(key)]
    comparisons=[]
    for saved,fresh in zip(baseline_after['details'],reloaded['details']):
        assert saved['task']==fresh['task'] and saved['target_tokens']==fresh['target_tokens']
        comparisons.append({'task':saved['task'],'saved_loss':saved['loss'],'reloaded_loss':fresh['loss'],
            'absolute_difference':abs(saved['loss']-fresh['loss']),
            'match':math.isclose(saved['loss'],fresh['loss'],rel_tol=1e-4,abs_tol=1e-5)})
    saved_loss=baseline_after['token_weighted_loss'];fresh_loss=reloaded['token_weighted_loss']
    aggregate_match=math.isclose(saved_loss,fresh_loss,rel_tol=1e-4,abs_tol=1e-5)
    report={'scope':'fresh_base_exported_final_adapter_and_tokenizer_reload_on_dev100',
        'model':MODEL_ID,'revision':REVISION,'training_examples':10000,'total_training_optimizer_updates':1250,
        'optimizer_updates_in_verification':0,'saved_validation_loss':saved_loss,'reloaded_validation_loss':fresh_loss,
        'absolute_difference':abs(saved_loss-fresh_loss),'loss_tolerance':{'rtol':1e-4,'atol':1e-5},
        'aggregate_loss_match':aggregate_match,'per_task_matches':sum(c['match'] for c in comparisons),'tasks':100,
        'max_per_task_loss_difference':max(c['absolute_difference'] for c in comparisons),
        'adapter_tensors_match_exactly':True,'exported_tokenizer_inputs_match':True,
        'serialized_frozen_base_matches':not changed,'changed_base_keys':changed,
        'before_base_sha256':before_base['state_sha256'],'reloaded_base_sha256':after_base['state_sha256'],
        'per_task_comparisons':comparisons,'reloaded_evaluation':reloaded,
        'match':not changed and aggregate_match and all(c['match'] for c in comparisons),
        'reload_and_evaluation_seconds':time.perf_counter()-started,
        'limitations':['This validates persistence and prediction-loss reproduction, not executable repair correctness.',
            'Serialized frozen-state hashes do not include every nonserialized implementation cache.',
            'Full dev1000 prediction comparison, trained dev20 repairs and external benchmarks remain separate work.']}
    with report_path.open('x') as stream:json.dump(report,stream,indent=2)
    summary={k:v for k,v in report.items() if k not in ('per_task_comparisons','reloaded_evaluation','limitations')}
    print(json.dumps(summary,indent=2))
    if report['match']:
        (FINAL_VERIFY30/'RELOAD_MATCH').write_text('Fresh pinned base plus exported final adapter/tokenizer reproduced dev100; no optimizer updates.\n')
        print('Final saved-adapter reload: MATCH. No training performed.')
    else:
        print('Final reload mismatch preserved. Share this report; do not loosen the tolerance or overwrite the evidence.')
    return report

final_reload_result30=check_final_reload30()
