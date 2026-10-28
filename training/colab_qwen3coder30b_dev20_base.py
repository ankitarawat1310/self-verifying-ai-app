# SAME A100 Colab session after the completed 100-record base-loss baseline.
# Upload only the NEW tiny prompt ZIP. Never upload reference repairs or tests.
import gc, hashlib, io, json, time, zipfile
from pathlib import Path
from importlib.metadata import version
import torch
from unsloth import FastModel
from transformers import GenerationConfig
from peft import get_peft_model_state_dict, set_peft_model_state_dict
from safetensors.torch import load_file
from google.colab import files

FULL_RUN_ROOT=Path("/content/drive/MyDrive/SVAGA/context-qwen3coder30b-10k-v1")
assert (FULL_RUN_ROOT/'BASELINE_COMPLETE').exists()
assert not list(FULL_RUN_ROOT.glob('step-*')), "Full training already started; do not regenerate a pre-training baseline."
run_config=json.loads((FULL_RUN_ROOT/'config.json').read_text())
assert getattr(model.config,'_commit_hash',None)==run_config['revision']
initial_saved=load_file(str(FULL_RUN_ROOT/'initial_adapter/adapter_model.safetensors'),device='cpu')
assert initial_saved and all('lora_' in k for k in initial_saved)
assert any('lora_B' in k for k in initial_saved)
assert all(torch.count_nonzero(t).item()==0 for k,t in initial_saved.items() if 'lora_B' in k)
initial_current=get_peft_model_state_dict(model)
assert set(initial_current)==set(initial_saved)
assert all(torch.equal(t.detach().cpu(),initial_saved[k]) for k,t in initial_current.items()), "Adapter differs from restored initial state. Stop."
del initial_current

uploaded=files.upload()
assert len(uploaded)==1,"Upload only repair-dev20-qwen3coder30b-base-prompts.zip."
_,packet_bytes=next(iter(uploaded.items()))
assert hashlib.sha256(packet_bytes).hexdigest()=='1193c57f9e8b1a14ac09f11562e3331391f54f52e28d6df0e7b43b23de763dbd',"Wrong prompt ZIP."
with zipfile.ZipFile(io.BytesIO(packet_bytes)) as archive:
    assert len(archive.namelist())==2 and set(archive.namelist())=={'manifest.json','prompts.jsonl'}
    generation_manifest_raw=archive.read('manifest.json')
    generation_manifest=json.loads(generation_manifest_raw)
    prompt_bytes=archive.read('prompts.jsonl')
assert generation_manifest['evaluation_id']=='repair-dev20-qwen3coder30b-base-v1'
assert hashlib.sha256(prompt_bytes).hexdigest()==generation_manifest['prompts_sha256']
assert generation_manifest['model']==MODEL_ID and generation_manifest['model_revision']==REVISION
prompts=[json.loads(line) for line in prompt_bytes.decode('utf-8').splitlines() if line.strip()]
assert len(prompts)==len({r['instance_id'] for r in prompts})==20
for row in prompts:
    assert set(row)=={'instance_id','repo','messages','prompt_sha256'}
    assert [m['role'] for m in row['messages']]==['user']
    assert hashlib.sha256(json.dumps(row['messages'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()==row['prompt_sha256']
print('Verified same frozen 20 prompts. No private tests or reference repairs uploaded.',flush=True)

# Load enough context for the entire prompt AND the unchanged 2,048-token output budget.
# Max training example length remains 4,096; native model supports a larger context.
context=8192
caps=[getattr(module,'max_seq_length') for module in model.modules() if isinstance(getattr(module,'max_seq_length',None),int)]
if not caps or min(caps)<context:
    print('Reloading the cached pinned base with 8,192-token context; no training.',flush=True)
    for name in ('model','trainable','trainable_named','current_state'):
        globals().pop(name,None)
    torch.compiler.reset();gc.collect();torch.cuda.empty_cache()
    assert torch.cuda.memory_allocated()/2**30<4,'Old model memory remains; stop before loading a second model.'
    model,tokenizer=FastModel.from_pretrained(model_name=MODEL_ID,revision=REVISION,use_exact_model_name=True,
        max_seq_length=context,dtype=torch.bfloat16,load_in_4bit=True,full_finetuning=False,
        device_map={'':0},trust_remote_code=False,local_files_only=True)
    assert getattr(model.config,'_commit_hash',None)==REVISION
    model=FastModel.get_peft_model(model,r=16,lora_alpha=16,lora_dropout=0,bias='none',
        target_modules=['q_proj','k_proj','v_proj','o_proj'],use_gradient_checkpointing='unsloth',random_state=42)
    model.peft_config['default'].revision=REVISION
    outcome=set_peft_model_state_dict(model,initial_saved,adapter_name='default')
    assert not outcome.unexpected_keys and not any('lora_' in k for k in outcome.missing_keys)
assert all(torch.equal(t.detach().cpu(),initial_saved[k]) for k,t in get_peft_model_state_dict(model).items())
tokenizer=getattr(tokenizer,'tokenizer',tokenizer)
assert hashlib.sha256(json.dumps(tokenizer.chat_template,sort_keys=True).encode()).hexdigest()==generation_manifest['tokenizer_chat_template_sha256']
if tokenizer.pad_token_id is None:tokenizer.pad_token=tokenizer.eos_token
assert isinstance(tokenizer.eos_token_id,int)
assert int(model.config.max_position_embeddings)>=context
caps=[getattr(module,'max_seq_length') for module in model.modules() if isinstance(getattr(module,'max_seq_length',None),int)]
assert caps and min(caps)>=context,'Model context smaller than the frozen generation protocol.'
for row in prompts:
    ids=tokenizer.apply_chat_template(row['messages'],tokenize=True,add_generation_prompt=True,truncation=False,return_dict=False)
    assert len(ids)==generation_manifest['prompt_token_lengths'][row['instance_id']]
    assert len(ids)+2048<=context
print('All prompts verified without truncation; maximum prompt + output allowance is 5,414 tokens.',flush=True)

model.requires_grad_(False);model.eval()
FastModel.for_inference(model)
generation_config=GenerationConfig(do_sample=False,num_beams=1,max_new_tokens=2048,repetition_penalty=1.0,
    use_cache=True,eos_token_id=tokenizer.eos_token_id,pad_token_id=tokenizer.pad_token_id,
    bos_token_id=tokenizer.bos_token_id)
GENERATION_ROOT=FULL_RUN_ROOT/'dev20-base';GENERATION_ROOT.mkdir(exist_ok=True)
output_path=GENERATION_ROOT/'qwen3coder30b_dev20_base_generations.json'
generation_metadata={
    'manifest_sha256':hashlib.sha256(generation_manifest_raw).hexdigest(),
    'model':MODEL_ID,'revision':REVISION,'decoding':generation_manifest['decoding'],
    'adapter_artifacts_sha256':{},'adapter_mode':'disabled','model_context_length':context,
    'initial_adapter_weights_sha256':hashlib.sha256((FULL_RUN_ROOT/'initial_adapter/adapter_model.safetensors').read_bytes()).hexdigest(),
    'software':{p:version(p) for p in ('torch','transformers','peft','accelerate','bitsandbytes','unsloth','unsloth_zoo')},
    'effective_generation_config':generation_config.to_dict(),'gpu':torch.cuda.get_device_name(0),
    'scope':'base-only frozen development generation before training; no generated commands executed'}
state=json.loads(output_path.read_text()) if output_path.exists() else {**generation_metadata,'records':[]}
for key,value in generation_metadata.items():
    assert state.get(key)==value,'Existing output metadata differs: '+key
saved={(r['instance_id'],r['variant']) for r in state['records']}
allowed={(r['instance_id'],'base') for r in prompts}
assert len(saved)==len(state['records']) and saved<=allowed
lookup={r['instance_id']:r for r in prompts}
for r in state['records']:
    assert r['prompt_sha256']==lookup[r['instance_id']]['prompt_sha256']
    assert r['prompt_tokens']==generation_manifest['prompt_token_lengths'][r['instance_id']]
    assert isinstance(r['text'],str) and isinstance(r['hit_token_limit'],bool)

def save_generations():
    temp=output_path.with_suffix('.tmp')
    temp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(output_path)

protocol_path=GENERATION_ROOT/'manifest.json'
if protocol_path.exists():assert protocol_path.read_bytes()==generation_manifest_raw
else:protocol_path.write_bytes(generation_manifest_raw)
with model.disable_adapter(),torch.inference_mode():
    for row in prompts:
        if (row['instance_id'],'base') in saved:continue
        encoded=tokenizer.apply_chat_template(row['messages'],tokenize=True,add_generation_prompt=True,
            truncation=False,return_tensors='pt',return_dict=True)
        encoded={k:v.to('cuda') for k,v in encoded.items()}
        length=encoded['input_ids'].shape[1]
        assert length==generation_manifest['prompt_token_lengths'][row['instance_id']]
        torch.manual_seed(42);torch.cuda.manual_seed_all(42)
        torch.cuda.synchronize();started=time.perf_counter()
        with torch.autocast('cuda',dtype=torch.bfloat16):
            generated=model.generate(**encoded,generation_config=generation_config,max_new_tokens=2048,
                do_sample=False,num_beams=1,repetition_penalty=1.0,use_cache=True)
        torch.cuda.synchronize();seconds=time.perf_counter()-started
        assert generated.shape[1]>=length and torch.equal(generated[0,:length],encoded['input_ids'][0])
        new=generated[0,length:].tolist()
        assert len(new)<=2048
        hit=len(new)>=2048 and (not new or new[-1]!=tokenizer.eos_token_id)
        state['records'].append({'instance_id':row['instance_id'],'variant':'base','prompt_sha256':row['prompt_sha256'],
            'text':tokenizer.decode(new,skip_special_tokens=True),'output_token_ids':new,
            'output_tokens':len(new),'prompt_tokens':length,'hit_token_limit':bool(hit),'seconds':seconds})
        saved.add((row['instance_id'],'base'));save_generations()
        print(f"{len(saved)}/20 base {row['instance_id']} | tokens: {len(new)} | seconds: {seconds:.1f} | limit: {hit}",flush=True)
        del encoded,generated
assert saved==allowed
(GENERATION_ROOT/'GENERATION_COMPLETE').write_text('20 frozen base outputs saved before full training; no output-based filtering or retries.\n')
model.config.use_cache=False
print('Saved:',output_path)
print('No training or generated-command execution. Download this JSON for isolated local evaluation.')
files.download(str(output_path))
