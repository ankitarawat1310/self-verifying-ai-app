# SAME loaded A100 session after the trained-model backup/diagnostic.
# Generates only the 20 TRAINED-adapter outputs. Existing base outputs are copied unchanged.
# No training, model download, model reload, or generated-command execution.
import hashlib,io,json,time,zipfile
from pathlib import Path
from importlib.metadata import version
from contextlib import nullcontext
import torch
from unsloth import FastModel
from transformers import GenerationConfig
from peft import get_peft_model_state_dict
from safetensors.torch import load_file
from google.colab import files

ROOT30=Path('/content/drive/MyDrive/SVAGA/context-qwen3coder30b-10k-v1')
EXPORT30=ROOT30/'final_export'
assert globals().get('model') is not None,'Keep the loaded trained model. Do not start a new runtime.'
assert (ROOT30/'TRAINING_COMPLETE').exists() and (EXPORT30/'EXPORT_COMPLETE').exists()
assert getattr(model.config,'_commit_hash',None)=='b2cff646eb4bb1d68355c01b18ae02e7cf42d120'
base_path=ROOT30/'dev20-base/qwen3coder30b_dev20_base_generations.json'
base_raw=base_path.read_bytes()
assert hashlib.sha256(base_raw).hexdigest()=='c18170d7dc6c1b1be567c7b48ea3b19677fdb25c5b0462aec2a8250feaee7c28'
base_data=json.loads(base_raw)
assert len(base_data['records'])==20 and all(r['variant']=='base' for r in base_data['records'])
print('Upload ONLY repair-dev20-qwen3coder30b-paired-prompts.zip',flush=True)
uploaded=files.upload();assert len(uploaded)==1
_,raw_zip=next(iter(uploaded.items()))
assert hashlib.sha256(raw_zip).hexdigest()=='1feba8497aa678c7ba703376c1451bd939c77703f8e55ea0a3f7e1e5bc85c499','Wrong prompt ZIP.'
with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
    assert len(archive.namelist())==2 and set(archive.namelist())=={'manifest.json','prompts.jsonl'}
    manifest_raw=archive.read('manifest.json');manifest=json.loads(manifest_raw)
    prompts_raw=archive.read('prompts.jsonl')
assert manifest['evaluation_id']=='repair-dev20-qwen3coder30b-paired-v1'
assert manifest['variants']==['base','adapter']
assert manifest['model']==base_data['model'] and manifest['model_revision']==base_data['revision']
assert manifest['parent_base_manifest_sha256']==base_data['manifest_sha256']
assert manifest['base_generation_sha256']==hashlib.sha256(base_raw).hexdigest()
assert manifest['decoding']==base_data['decoding']
assert hashlib.sha256(prompts_raw).hexdigest()==manifest['prompts_sha256']
prompts=[json.loads(line) for line in prompts_raw.decode().splitlines() if line.strip()]
assert len(prompts)==len({r['instance_id'] for r in prompts})==20
assert [r['instance_id'] for r in prompts]==[r['instance_id'] for r in base_data['records']]
for row in prompts:
    assert set(row)=={'instance_id','repo','messages','prompt_sha256'}
    assert [m['role'] for m in row['messages']]==['user']
    assert hashlib.sha256(json.dumps(row['messages'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()==row['prompt_sha256']
for relative,digest in manifest['adapter_artifacts_sha256'].items():
    rel=Path(relative);assert not rel.is_absolute() and '..' not in rel.parts
    assert hashlib.sha256((EXPORT30/rel).read_bytes()).hexdigest()==digest,'Trained export changed: '+relative
weights=load_file(str(EXPORT30/'adapter/adapter_model.safetensors'),device='cpu')
live=get_peft_model_state_dict(model)
assert set(live)==set(weights)
assert all(v.detach().cpu().dtype==weights[k].dtype and torch.equal(v.detach().cpu(),weights[k]) for k,v in live.items())
assert any(torch.count_nonzero(v).item()>0 for k,v in weights.items() if 'lora_B' in k),'Wrong untrained adapter.'
del live
software={p:version(p) for p in ('torch','transformers','peft','accelerate','bitsandbytes','unsloth','unsloth_zoo')}
assert software==base_data['software'],'Software differs from the base generation run.'
assert hashlib.sha256(json.dumps(tokenizer.chat_template,sort_keys=True).encode()).hexdigest()==manifest['tokenizer_chat_template_sha256']
if tokenizer.pad_token_id is None:tokenizer.pad_token=tokenizer.eos_token
assert tokenizer.eos_token_id==base_data['effective_generation_config']['eos_token_id']
assert tokenizer.pad_token_id==base_data['effective_generation_config']['pad_token_id']
caps=[getattr(module,'max_seq_length') for module in model.modules() if isinstance(getattr(module,'max_seq_length',None),int)]
assert caps and min(caps)>=8192
for row in prompts:
    ids=tokenizer.apply_chat_template(row['messages'],tokenize=True,add_generation_prompt=True,truncation=False,return_dict=False)
    assert len(ids)==manifest['prompt_token_lengths'][row['instance_id']]
    assert len(ids)+2048<=8192
model.set_adapter('default');model.requires_grad_(False);model.eval()
assert model.active_adapter=='default'
FastModel.for_inference(model)
generation_config=GenerationConfig.from_dict(base_data['effective_generation_config'])
assert generation_config.to_dict()==base_data['effective_generation_config'],'Effective generation settings differ.'
OUT30=ROOT30/'dev20-paired';OUT30.mkdir(exist_ok=True)
output_path=OUT30/'qwen3coder30b_dev20_paired_generations.json'
metadata={'manifest_sha256':hashlib.sha256(manifest_raw).hexdigest(),'model':manifest['model'],
    'revision':manifest['model_revision'],'decoding':manifest['decoding'],
    'adapter_artifacts_sha256':manifest['adapter_artifacts_sha256'],'software':software,
    'gpu':torch.cuda.get_device_name(0),'model_context_length':8192,
    'effective_generation_config':generation_config.to_dict(),
    'compiler_stance':'default','base_generation_sha256':hashlib.sha256(base_raw).hexdigest(),
    'base_manifest_sha256':base_data['manifest_sha256'],
    'base_records_policy':'original pre-training records copied byte-for-byte in JSON value; original file also preserved separately',
    'scope':'paired frozen development generation; no tests or training executed',
    'numeric_reload_limitation':'strict dev100 loss reproduction failed despite exact serialized artifact matches; original evidence preserved'}
state=json.loads(output_path.read_text()) if output_path.exists() else {**metadata,'records':json.loads(json.dumps(base_data['records']))}
for key,value in metadata.items():assert state.get(key)==value,'Existing run metadata differs: '+key
assert [r for r in state['records'] if r['variant']=='base']==base_data['records']
allowed={(r['instance_id'],variant) for r in prompts for variant in ('base','adapter')}
saved={(r['instance_id'],r['variant']) for r in state['records']}
assert len(saved)==len(state['records']) and saved<=allowed
lookup={r['instance_id']:r for r in prompts}
for record in state['records']:
    assert record['prompt_sha256']==lookup[record['instance_id']]['prompt_sha256']
    assert record['prompt_tokens']==manifest['prompt_token_lengths'][record['instance_id']]
    assert record['output_tokens']==len(record['output_token_ids'])<=2048
    assert isinstance(record['hit_token_limit'],bool) and isinstance(record['text'],str)
for name,raw in (('manifest.json',manifest_raw),('base_generations_original.json',base_raw)):
    p=OUT30/name
    if p.exists():assert p.read_bytes()==raw
    else:p.write_bytes(raw)

def save_paired30():
    temp=output_path.with_suffix('.tmp');temp.write_text(json.dumps(state,ensure_ascii=False,indent=2));temp.replace(output_path)

print('Verified full-10K-trained adapter and same 20 prompts. Generating only the trained condition...',flush=True)
with torch.compiler.set_stance('default'),torch.inference_mode():
    for row in prompts:
        if (row['instance_id'],'adapter') in saved:continue
        encoded=tokenizer.apply_chat_template(row['messages'],tokenize=True,add_generation_prompt=True,
            truncation=False,return_tensors='pt',return_dict=True)
        encoded={k:v.to('cuda') for k,v in encoded.items()};length=encoded['input_ids'].shape[1]
        assert length==manifest['prompt_token_lengths'][row['instance_id']]
        torch.manual_seed(42);torch.cuda.manual_seed_all(42)
        torch.cuda.synchronize();started=time.perf_counter()
        # Match the earlier base call's effective arguments. Its deprecation warnings are retained, not fixed mid-comparison.
        with torch.autocast('cuda',dtype=torch.bfloat16):
            generated=model.generate(**encoded,generation_config=generation_config,max_new_tokens=2048,
                do_sample=False,num_beams=1,repetition_penalty=1.0,use_cache=True)
        torch.cuda.synchronize();seconds=time.perf_counter()-started
        assert torch.equal(generated[0,:length],encoded['input_ids'][0])
        new=generated[0,length:].tolist();assert len(new)<=2048
        limit=len(new)>=2048 and (not new or new[-1]!=tokenizer.eos_token_id)
        state['records'].append({'instance_id':row['instance_id'],'variant':'adapter','prompt_sha256':row['prompt_sha256'],
            'text':tokenizer.decode(new,skip_special_tokens=True),'output_token_ids':new,
            'output_tokens':len(new),'prompt_tokens':length,'hit_token_limit':bool(limit),'seconds':seconds})
        saved.add((row['instance_id'],'adapter'));save_paired30()
        print(f"{len(saved)-20}/20 trained {row['instance_id']} | tokens: {len(new)} | seconds: {seconds:.1f} | limit: {limit}",flush=True)
        del encoded,generated
assert saved==allowed and len(state['records'])==40
assert [r for r in state['records'] if r['variant']=='base']==base_data['records']
assert hashlib.sha256(base_path.read_bytes()).hexdigest()==manifest['base_generation_sha256']
(OUT30/'GENERATION_COMPLETE').write_text('20 original base outputs preserved + 20 trained outputs saved; no training or command execution.\n')
model.config.use_cache=False
print('Saved:',output_path)
print('40 paired records = 20 unique tasks in two conditions. No generated commands executed.')
files.download(str(output_path))
