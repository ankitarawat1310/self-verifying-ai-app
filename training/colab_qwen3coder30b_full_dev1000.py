# SAME loaded A100 session. Paired prediction-loss evaluation on ALL 1,000 dev records.
# Base and trained adapter are evaluated in one model instance under an explicit default compiler policy.
# No optimizer updates, model reload, or generated-command execution.
import hashlib,json,math,time,uuid
from pathlib import Path
from contextlib import nullcontext
from importlib.metadata import version
import torch
from unsloth import FastModel
from peft import get_peft_model_state_dict
from safetensors.torch import load_file
from google.colab import files

ROOT30=Path('/content/drive/MyDrive/SVAGA/context-qwen3coder30b-10k-v1')
EXPORT30=ROOT30/'final_export'
FULL_DEV_LABEL30='full-dev1000-same-instance-v1'
assert globals().get('model') is not None and globals().get('prepared') is not None
assert (ROOT30/'TRAINING_COMPLETE').exists() and (EXPORT30/'EXPORT_COMPLETE').exists()
model_id='Qwen/Qwen3-Coder-30B-A3B-Instruct';revision='b2cff646eb4bb1d68355c01b18ae02e7cf42d120'
assert getattr(model.config,'_commit_hash',None)==revision
saved_config=json.loads((EXPORT30/'training-runtime-config.json').read_text())
actual_software={p:version(p) for p in saved_config['software']}
assert actual_software==saved_config['software']
weights=load_file(str(EXPORT30/'adapter/adapter_model.safetensors'),device='cpu')
live=get_peft_model_state_dict(model)
assert set(live)==set(weights) and all(v.detach().cpu().dtype==weights[k].dtype and torch.equal(v.detach().cpu(),weights[k]) for k,v in live.items())
del live
assert len(prepared['validation'])==1000
assert not {e['task'] for e in prepared['train']} & {e['task'] for e in prepared['validation']}
digest=hashlib.sha256()
for e in prepared['validation']:
    digest.update(json.dumps({'task':e['task'],'input_ids':e['input_ids'],'prompt_length':e['prompt_length']},sort_keys=True,separators=(',',':')).encode());digest.update(b'\n')
assert digest.hexdigest()==saved_config['prepared_validation_sha256']
examples=sorted(prepared['validation'],key=lambda e:hashlib.sha256(e['task'].encode()).hexdigest())
assert len({e['task'] for e in examples})==1000 and sum(e['target_tokens'] for e in examples)==332113
out=ROOT30/FULL_DEV_LABEL30;out.mkdir(exist_ok=True)
path=out/'full_dev1000_same_instance_comparison.json'
# A fresh model/session may not silently append numerical results to a previous partial instance.
if not hasattr(model,'_svaga_eval_instance_id30'):
    model._svaga_eval_instance_id30=uuid.uuid4().hex
instance_id=model._svaga_eval_instance_id30
metadata={'scope':'same_instance_paired_full_development_prediction_loss_not_functional_accuracy',
    'model':model_id,'revision':revision,'software':actual_software,'gpu':torch.cuda.get_device_name(0),
    'validation_records':1000,'target_tokens_per_condition':332113,
    'validation_input_sha256':saved_config['prepared_validation_sha256'],
    'adapter_sha256':hashlib.sha256((EXPORT30/'adapter/adapter_model.safetensors').read_bytes()).hexdigest(),
    'compiler_stance':'default','dtype':'bfloat16','model_context_length':8192,'use_cache':False,
    'order':'SHA256(instance_id) ascending in both conditions','model_instance_id':instance_id,
    'optimizer_updates_during_evaluation':0,
    'limitations':['This is a new same-instance evaluation protocol; prior strict cross-reload loss failure remains preserved.',
        'Default compilation policy does not disable custom Unsloth/Triton kernels or guarantee bitwise equivalence to an earlier warm instance.',
        'These are development data, not untouched external benchmark tasks. Prediction loss is not executable repair accuracy.']}
if path.exists():
    state=json.loads(path.read_text())
    if state.get('complete'):
        print('Existing completed evaluation found; no forwards repeated.')
    else:
        assert all(state.get(k)==v for k,v in metadata.items()),'Different model/session or protocol. Preserve partial results and choose a new FULL_DEV_LABEL30 for a fresh paired evaluation.'
else:state={**metadata,'conditions':{'base':[],'adapter':[]},'complete':False}

def save_full_dev30():
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(state,indent=2));temp.replace(path)

if not state['complete']:
    old_flags=[(p,p.requires_grad) for p in model.parameters()]
    old_mode=model.training;old_cache=model.config.use_cache
    model.set_adapter('default')
    FastModel.for_training(model,use_gradient_checkpointing='unsloth')
    model.requires_grad_(False);model.eval();model.config.use_cache=False
    assert not any(m.training for m in model.modules())
    try:
        with torch.random.fork_rng(devices=[0]),torch.compiler.set_stance('default'):
            for variant in ('base','adapter'):
                records=state['conditions'][variant]
                assert len(records)<=1000
                assert [r['task'] for r in records]==[e['task'] for e in examples[:len(records)]]
                torch.manual_seed(42);torch.cuda.manual_seed_all(42)
                print('FULL DEVELOPMENT:',variant,'starting at',len(records),'/1000',flush=True)
                with (model.disable_adapter() if variant=='base' else nullcontext()),torch.no_grad():
                    for number in range(len(records),1000):
                        e=examples[number];started=time.perf_counter()
                        ids=torch.tensor([e['input_ids']],dtype=torch.long,device='cuda')
                        labels=ids.clone();labels[:,:e['prompt_length']]=-100
                        count=int((labels[:,1:]!=-100).sum());assert count==e['target_tokens']>0
                        with torch.autocast('cuda',dtype=torch.bfloat16):
                            output=model(input_ids=ids,attention_mask=torch.ones_like(ids),labels=labels,use_cache=False)
                        loss=float(output.loss.float());assert math.isfinite(loss)
                        records.append({'task':e['task'],'loss':loss,'target_tokens':count,'seconds':time.perf_counter()-started})
                        del ids,labels,output
                        if len(records)==1 or len(records)%25==0 or len(records)==1000:
                            save_full_dev30();print(variant,len(records),'/1000',flush=True)
        live=get_peft_model_state_dict(model)
        assert set(live)==set(weights) and all(torch.equal(v.detach().cpu(),weights[k]) for k,v in live.items())
        del live
        totals={}
        for variant in ('base','adapter'):
            values=state['conditions'][variant]
            assert len(values)==1000 and sum(v['target_tokens'] for v in values)==332113
            totals[variant]=sum(v['loss']*v['target_tokens'] for v in values)/332113
        assert [r['task'] for r in state['conditions']['base']]==[r['task'] for r in state['conditions']['adapter']]
        state['summary']={'base_token_weighted_loss':totals['base'],'adapter_token_weighted_loss':totals['adapter'],
            'change':totals['adapter']-totals['base'],
            'relative_reduction_percent':(totals['base']-totals['adapter'])/totals['base']*100,
            'records_per_condition':1000,'target_tokens_per_condition':332113}
        state['complete']=True;state['adapter_tensors_unchanged']=True;save_full_dev30()
        (out/'COMPLETE').write_text('Both 1000-record conditions evaluated in one loaded model instance; no training.\n')
    finally:
        model.requires_grad_(False);model.eval();model.config.use_cache=False
        del old_flags
print(json.dumps(state.get('summary',{}),indent=2))
print('Saved:',path)
print('Same-instance prediction-loss comparison only. Prior numerical reproduction failure remains unchanged.')
files.download(str(path))
