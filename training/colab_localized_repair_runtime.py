"""Notebook runtime for the experimental 10K localized repair dataset.

This file is embedded into the generated Colab notebook, not executed locally.
"""
import gc
import hashlib
import json
import math
from pathlib import Path
import random
import time
import uuid
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, set_seed
from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training

MODEL_ID='Qwen/Qwen2.5-Coder-1.5B-Instruct'
REVISION='2e1fd397ee46e1388853d2af2c993145b0f1098a'
SEED=42
ACCUMULATION=8
LEARNING_RATE=2e-5


def load_dataset(folder):
    folder=Path(folder)
    manifest=json.loads((folder/'manifest.json').read_text())
    assert manifest['tokenizer']==MODEL_ID and manifest['tokenizer_revision']==REVISION
    rows={}
    for split,n in [('train',10000),('validation',1000)]:
        path=folder/f'{split}.jsonl'
        assert hashlib.sha256(path.read_bytes()).hexdigest()==manifest['files_sha256'][path.name]
        rows[split]=[json.loads(x) for x in path.open(encoding='utf-8')]
        assert len(rows[split])==n
        assert len({r['instance_id'] for r in rows[split]})==n
    for key in ['instance_id','repo','bug_patch_sha256','buggy_excerpts_sha256']:
        assert not {r[key] for r in rows['train']}&{r[key] for r in rows['validation']},key
    return manifest,rows


def prepare(rows,tokenizer):
    examples=[]
    for row in rows:
        messages=row['messages']
        full=tokenizer.apply_chat_template(messages,tokenize=True,return_dict=True,truncation=False)['input_ids']
        prompt=tokenizer.apply_chat_template(messages[:1],tokenize=True,return_dict=True,add_generation_prompt=True,truncation=False)['input_ids']
        assert full[:len(prompt)]==prompt and 0<len(prompt)<len(full)<=4096
        assert len(full)==row['tokens']['total'] and len(full)-len(prompt)==row['tokens']['target']
        examples.append({'task':row['instance_id'],'input_ids':full,'prompt_length':len(prompt)})
    return examples


def batch_for(example):
    ids=torch.tensor([example['input_ids']],dtype=torch.long,device='cuda')
    labels=ids.clone();labels[:,:example['prompt_length']]=-100
    return {'input_ids':ids,'attention_mask':torch.ones_like(ids),'labels':labels}


def evaluate(model,examples):
    was_training=model.training;model.eval();total_loss=0.;targets=0;details=[]
    try:
        with torch.inference_mode():
            for example in examples:
                batch=batch_for(example)
                count=int((batch['labels'][:,1:]!=-100).sum())
                with torch.autocast('cuda',dtype=torch.float16):
                    output=model(**batch,use_cache=False)
                loss=float(output.loss.float())
                assert math.isfinite(loss) and count>0
                total_loss+=loss*count;targets+=count
                details.append({'task':example['task'],'loss':loss,'target_tokens':count})
                del batch,output
    finally:model.train(was_training)
    return {'token_weighted_loss':total_loss/targets,'examples':len(examples),'target_tokens':targets,'details':details}


def setup_model(resume=None):
    set_seed(SEED)
    tokenizer=AutoTokenizer.from_pretrained(MODEL_ID,revision=REVISION,trust_remote_code=False)
    if tokenizer.pad_token_id is None:tokenizer.pad_token=tokenizer.eos_token
    quantization=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.float16)
    base=AutoModelForCausalLM.from_pretrained(MODEL_ID,revision=REVISION,quantization_config=quantization,
            device_map={'':0},dtype=torch.float16,attn_implementation='sdpa',trust_remote_code=False)
    base.config.use_cache=False
    base=prepare_model_for_kbit_training(base,use_gradient_checkpointing=True,gradient_checkpointing_kwargs={'use_reentrant':False})
    if resume:model=PeftModel.from_pretrained(base,str(Path(resume)/'adapter'),is_trainable=True)
    else:model=get_peft_model(base,LoraConfig(r=8,lora_alpha=16,lora_dropout=0.05,target_modules=['q_proj','v_proj'],bias='none',task_type='CAUSAL_LM'))
    model.print_trainable_parameters()
    return model,tokenizer


def initialize_run(model,manifest,train_count,checkpoint_root,resume=None):
    root=Path(checkpoint_root);root.mkdir(parents=True,exist_ok=True)
    optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=LEARNING_RATE,weight_decay=0.)
    scaler=torch.amp.GradScaler('cuda')
    fingerprint=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
    if resume:
        assert (Path(resume)/'COMPLETE').exists(),'Incomplete checkpoint: choose a completed checkpoint.'
        # Load only this notebook's own checkpoint; pickle state is not for arbitrary uploads.
        state=torch.load(Path(resume)/'training_state.pt',map_location='cpu',weights_only=False)
        assert state['manifest_fingerprint']==fingerprint and state['accumulation']==ACCUMULATION
        optimizer.load_state_dict(state['optimizer']);scaler.load_state_dict(state['scaler'])
        run=state['run'];torch.set_rng_state(state['torch_rng']);torch.cuda.set_rng_state_all(state['cuda_rng'])
        assert run['next_position']%ACCUMULATION==0 or run['next_position']==train_count
        del state
    else:
        assert not list(root.glob('step-*')),'Existing run found: resume it or choose a new output folder.'
        order=list(range(train_count));random.Random(SEED).shuffle(order)
        run={'order':order,'next_position':0,'optimizer_steps':0,'log':[],'baseline':None}
    assert sorted(run['order'])==list(range(train_count))
    return {'run':run,'optimizer':optimizer,'scaler':scaler,'root':root,'fingerprint':fingerprint}


def save_checkpoint(model,tokenizer,state):
    run=state['run'];destination=state['root']/f'step-{run["optimizer_steps"]:05d}'
    assert not destination.exists(),'Checkpoint already exists; use the latest checkpoint or a new run folder.'
    folder=state['root']/f'.incomplete-{run["optimizer_steps"]:05d}-{uuid.uuid4().hex}'
    folder.mkdir(exist_ok=False)
    model.save_pretrained(folder/'adapter');tokenizer.save_pretrained(folder/'tokenizer')
    torch.save({'optimizer':state['optimizer'].state_dict(),'scaler':state['scaler'].state_dict(),'run':run,
                'manifest_fingerprint':state['fingerprint'],'accumulation':ACCUMULATION,
                'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all()},folder/'training_state.pt')
    (folder/'COMPLETE').write_text('Checkpoint files saved successfully.\n')
    folder.rename(destination)
    (state['root']/'latest_checkpoint.txt').write_text(str(destination))
    print('Checkpoint:',destination,flush=True)


def train_epoch(model,tokenizer,examples,state):
    run=state['run'];optimizer=state['optimizer'];scaler=state['scaler']
    model.train();optimizer.zero_grad(set_to_none=True)
    gc.collect();torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats()
    start=time.perf_counter();start_position=run['next_position'];pending_loss=0.;pending_tasks=[]
    for position in range(start_position,len(examples)):
        group_start=(position//ACCUMULATION)*ACCUMULATION
        group_size=min(ACCUMULATION,len(examples)-group_start)
        example=examples[run['order'][position]];batch=batch_for(example)
        with torch.autocast('cuda',dtype=torch.float16):
            output=model(**batch,use_cache=False);loss=output.loss
        assert torch.isfinite(loss).item(), 'Nonfinite loss; stop and resume the last complete checkpoint.'
        value=float(loss.detach().float());scaler.scale(loss/group_size).backward()
        pending_loss+=value;pending_tasks.append(example['task'])
        del batch,output,loss
        if (position+1)%ACCUMULATION==0 or position+1==len(examples):
            scaler.unscale_(optimizer)
            norm=torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad],1.,error_if_nonfinite=True)
            scaler.step(optimizer);scaler.update();optimizer.zero_grad(set_to_none=True)
            run['next_position']=position+1;run['optimizer_steps']+=1
            run['log'].append({'step':run['optimizer_steps'],'examples_seen':position+1,'mean_example_loss':pending_loss/group_size,
                               'gradient_norm':float(norm),'tasks':pending_tasks})
            pending_loss=0.;pending_tasks=[]
            if run['optimizer_steps']%10==0 or run['optimizer_steps']==1:
                elapsed=time.perf_counter()-start;done=position+1-start_position
                remaining=elapsed/done*(len(examples)-position-1)/60
                print(f'Update {run["optimizer_steps"]}/1250 | examples {position+1}/10000 | loss {run["log"][-1]["mean_example_loss"]:.4f} | remaining ~{remaining:.1f} min',flush=True)
            run['peak_gpu_memory_gib']=max(run.get('peak_gpu_memory_gib',0.),torch.cuda.max_memory_allocated()/1024**3)
            if run['optimizer_steps']==1 or run['optimizer_steps']%50==0 or position+1==len(examples):save_checkpoint(model,tokenizer,state)
    assert run['next_position']==len(examples)
    run['peak_gpu_memory_gib']=max(run.get('peak_gpu_memory_gib',0.),torch.cuda.max_memory_allocated()/1024**3)
    print('One epoch complete. Peak GPU GiB:',round(run['peak_gpu_memory_gib'],2))
