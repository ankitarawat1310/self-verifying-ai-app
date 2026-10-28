"""Prepare a prompt-only exact-edit ablation without changing data or weights."""
import ast
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile
from repair_eval_common import sha
from search_replace_edits import reference_block, render_diff, parse_edits, plan_edits

EXPERIMENT = 'repair-dev20-search-replace-v1'
INSTRUCTION = '''Repair the issue using the supplied buggy Python source context.
Return exact SEARCH/REPLACE blocks only, in this format:

src/example.py
<<<<<<< SEARCH
    return a - b
=======
    return a + b
>>>>>>> REPLACE

Rules:
- Each block starts with the exact repository-relative FILE path from the supplied context.
- SEARCH must contain complete existing lines copied exactly, including indentation.
- Include enough unchanged surrounding lines to match exactly one location in the actual file.
- REPLACE contains the desired lines; an empty REPLACE deletes the searched lines.
- Multiple blocks are applied in order. Include a file path before every block.
- Edit only supplied files. Do not include diff headers, line numbers, explanations, or commands.
- Do not use fuzzy matches or invent unseen old code. The example above is format guidance only.
Affected file locations are supplied; repository search is outside this task.
'''


def main():
    root = Path(__file__).resolve().parents[1]
    original = root/'data/evaluation/repair-dev20-v1'
    output = root/'data/evaluation'/EXPERIMENT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-existing',action='store_true')
    args=parser.parse_args()
    if args.verify_existing:
        manifest=json.loads((output/'public/manifest.json').read_text(encoding='utf-8'))
        data=(output/'public/prompts.jsonl').read_bytes();private_data=(output/'private_tasks.jsonl').read_bytes()
        assert sha(data)==manifest['prompts_sha256'] and sha(private_data)==manifest['private_tasks_sha256']
        updated=[json.loads(line) for line in data.decode('utf-8').splitlines()]
        private=[json.loads(line) for line in private_data.decode('utf-8').splitlines()]
        _verify_preparation(root,output,private,updated,root/'training/notebooks/SVAGA_Dev20_SearchReplace_Base_vs_Adapter.ipynb',(output/'generation_runtime.py').read_text(encoding='utf-8'))
        return
    if output.exists():raise ValueError('Experiment already frozen; use --verify-existing for mechanical QA')
    manifest_raw = (original/'public/manifest.json').read_bytes(); old = json.loads(manifest_raw)
    raw = (original/'public/prompts.jsonl').read_bytes(); assert sha(raw)==old['prompts_sha256']
    private_raw = (original/'private_tasks.jsonl').read_bytes(); assert sha(private_raw)==old['private_tasks_sha256']
    prompts = [json.loads(line) for line in raw.decode('utf-8').splitlines()]
    private = [json.loads(line) for line in private_raw.decode('utf-8').splitlines()]
    tasks = {task['instance_id']:task for task in private}
    updated=[];updated_private=[];context_hashes={}
    for row in prompts:
        before, separator, body = row['messages'][0]['content'].partition('\n\nISSUE:\n')
        assert separator and body
        content = INSTRUCTION + '\n\nISSUE:\n' + body
        assert content.partition('\n\nISSUE:\n')[2]==body
        messages=[{'role':'user','content':content}]
        digest=sha(json.dumps(messages,sort_keys=True,ensure_ascii=False))
        updated.append({**row,'messages':messages,'prompt_sha256':digest})
        updated_private.append({**tasks[row['instance_id']], 'original_prompt_sha256':row['prompt_sha256'],'prompt_sha256':digest})
        context_hashes[row['instance_id']]=sha(body)
    def jsonl(items):return ''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in items).encode('utf-8')
    data=jsonl(updated);private_data=jsonl(updated_private)
    manifest={**old,'evaluation_id':EXPERIMENT,'edit_format':'exact_line_search_replace',
        'experiment_kind':'prompt_and_output_format_ablation_no_additional_training',
        'source_evaluation_id':old['evaluation_id'],'source_manifest_sha256':sha(manifest_raw),
        'original_prompts_sha256':sha(raw),'original_private_tasks_sha256':sha(private_raw),
        'prompts_sha256':sha(data),'private_tasks_sha256':sha(private_data),
        'issue_and_buggy_context_body_sha256':context_hashes,
        'application_policy':'Exact complete-line search; unique match required; sequential edits planned atomically; no fuzzy matching. Tool renders its own diff from exact edits.',
        'limitations':old['limitations']+['Same already-used development tasks, not a new test set.',
        'Adapter was trained on unified diffs, not this edit format; this is an inference ablation.',
        'A change in output format/instructions is tested; no guaranteed correctness improvement.']}
    output.mkdir(parents=True);public=output/'public';public.mkdir()
    (public/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (public/'prompts.jsonl').write_bytes(data);(output/'private_tasks.jsonl').write_bytes(private_data)
    with zipfile.ZipFile(output/'repair-dev20-search-replace-prompts.zip','x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ['manifest.json','prompts.jsonl']:archive.write(public/name,name)
    # Build an inference notebook with the unchanged generation method and new IDs/paths.
    runtime=(root/'training/repair_eval_generation.py').read_text(encoding='utf-8')
    expected="manifest['evaluation_id'] == 'repair-dev20-v1'"
    assert runtime.count(expected)==1
    runtime=runtime.replace(expected,"manifest['evaluation_id'] == '"+EXPERIMENT+"'")
    runtime=runtime.replace('repair-dev20-prompts.zip','repair-dev20-search-replace-prompts.zip')
    runtime=runtime.replace("destination = output_dir/'generation_results.json'", "destination = output_dir/'search_replace_generation_results.json'")
    ast.parse(runtime);(output/'generation_runtime.py').write_text(runtime,encoding='utf-8')
    notebook=json.loads((root/'training/notebooks/SVAGA_Repair_Dev20_Base_vs_Adapter.ipynb').read_text(encoding='utf-8'))
    for index,cell in enumerate(notebook['cells']):
        text=cell['source']
        if cell['cell_type']=='code' and 'def load_uploads' in text:text=runtime
        else:text=text.replace('repair-dev20-prompts.zip','repair-dev20-search-replace-prompts.zip').replace('repair-dev20-qwen15b-v1','repair-dev20-search-replace-qwen15b-v1').replace('generation_results.json','search_replace_generation_results.json')
        if index==0:
            text='# SVAGA: exact SEARCH/REPLACE format experiment\n\nSame 20 development tasks and same base/adapter weights as the completed unified-diff run. Only the output instructions change; issue/source bodies are byte-identical. No new training. Greedy decoding and the 2,048-new-token cap remain fixed.\n\nUpload repair-dev20-search-replace-prompts.zip and SVAGA_Qwen15B_10K_Final.zip. Generated edits remain text until tested locally. The adapter was trained on unified diffs, so this is a format/prompt ablation, not a newly trained search/replace model.\n'
        if cell['cell_type']=='code':ast.parse(text)
        cell['source']=text;cell['id']='search-replace-'+str(index)
    notebook['metadata']['colab']['name']='SVAGA_Dev20_SearchReplace_Base_vs_Adapter.ipynb'
    notebook_path=root/'training/notebooks/SVAGA_Dev20_SearchReplace_Base_vs_Adapter.ipynb'
    notebook_path.write_text(json.dumps(notebook,indent=2),encoding='utf-8')
    _verify_preparation(root,output,updated_private,updated,notebook_path,runtime)


def _verify_preparation(root,output,updated_private,updated,notebook_path,runtime):
    tasks={task['instance_id']:task for task in updated_private}
    # Private mechanical checks: never execute source and never upload reference edits.
    from enrich_official_context import patch_files,apply_bug,blob
    from transformers import AutoTokenizer
    validation=[json.loads(line) for line in (root/'data/prepared/swesmith-context-repair-10k-v2/validation.jsonl').read_text(encoding='utf-8').splitlines()]
    selected={row['instance_id']:row for row in validation if row['instance_id'] in tasks}
    mechanical=[]
    checks=output/'private-mechanical-checks';checks.mkdir(exist_ok=True)
    for task in updated_private:
        row=selected[task['instance_id']];provenance={f['path']:f for f in row['source_provenance']}
        clean_files={};buggy_files={};reference=''
        for info in patch_files(task['patch']):
            file=provenance[info['path']]
            clean_raw=(root/'data/source-cache/swesmith-blob-files'/(file['cache_key']+'.bin')).read_bytes()
            assert sha(clean_raw)==file['clean_file_sha256'] and blob(clean_raw)==file['clean_git_blob']
            buggy,_=apply_bug(clean_raw.decode('utf-8'),info)
            assert blob(buggy.encode())==file['buggy_git_blob']
            clean_files[info['path']]=clean_raw;buggy_files[info['path']]=buggy.encode()
            reference+=reference_block(info['path'],buggy,clean_raw.decode('utf-8'))
        with tempfile.TemporaryDirectory(dir=checks,prefix='reference-') as temporary:
            base=Path(temporary).resolve();assert base.parent==checks.resolve() and not base.is_symlink()
            for name,data_bytes in buggy_files.items():
                path=base/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data_bytes)
            derived,matches=render_diff(base,reference,task['allowed_paths'])
            _,planned,_=plan_edits(base,parse_edits(reference,task['allowed_paths']))
            assert all(planned[name]==clean for name,clean in clean_files.items())
            subprocess.run(['git','-C',str(base),'init','-q'],capture_output=True,check=True)
            subprocess.run(['git','-C',str(base),'config','core.autocrlf','false'],capture_output=True,check=True)
            subprocess.run(['git','-C',str(base),'config','core.eol','lf'],capture_output=True,check=True)
            patch=base/'reference.patch';patch.write_bytes(derived.encode())
            subprocess.run(['git','-C',str(base),'apply','--check',str(patch)],capture_output=True,check=True)
            subprocess.run(['git','-C',str(base),'apply',str(patch)],capture_output=True,check=True)
            assert all((base/name).read_bytes()==clean for name,clean in clean_files.items()), 'Reference roundtrip differs: '+task['instance_id']
            assert base.parent==checks.resolve()
        mechanical.append({'instance_id':task['instance_id'],'source_files':len(clean_files),
                           'reference_edit_blocks':len(matches),'exact_clean_bytes_restored':True})
    tokenizer=AutoTokenizer.from_pretrained(str(root/'results/fine_tuning/qwen15b-context-10k-v2/tokenizer'),local_files_only=True)
    lengths=[len(tokenizer.apply_chat_template(row['messages'],tokenize=True,add_generation_prompt=True,return_dict=True)['input_ids']) for row in updated]
    assert max(lengths)<=4096
    report={'status':'prepared_not_model_evaluated','frozen_tasks':20,'repositories':len({r['repo'] for r in updated}),
        'issue_source_context_unchanged':True,'reference_edit_roundtrips':mechanical,
        'reference_code_executed_on_host':False,'reference_answers_in_public_zip':False,
        'prompt_tokens':{'minimum':min(lengths),'maximum':max(lengths)},
        'model_training_performed':False,'gpu_generation_completed':False,'docker_model_evaluation_completed':False,
        'notebook':str(notebook_path),'generation_runtime_sha256':sha(runtime),
        'original_dataset_manifest_sha256':sha((root/'data/prepared/swesmith-context-repair-10k-v2/manifest.json').read_bytes())}
    (output/'setup-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Prepared:',output)
    print('Reference edits restored exact clean source:',len(mechanical),'/20; no source executed on host.')
    print('Prompt token range:',min(lengths),max(lengths))
    print('Notebook:',notebook_path)


if __name__=='__main__':main()
