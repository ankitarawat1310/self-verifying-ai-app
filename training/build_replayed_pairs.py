"""Materialize buggy-code/repair-diff pairs for three locally replayed tasks."""
import hashlib
import json
from pathlib import Path
import subprocess
from transformers import AutoTokenizer


def main():
    root=Path(__file__).resolve().parents[1]
    out=root/'data/prepared/swesmith-replayed-pairs-v1'
    if out.exists():raise ValueError('Output exists')
    out.mkdir(parents=True)
    tokenizer=AutoTokenizer.from_pretrained('Qwen/Qwen2.5-Coder-1.5B-Instruct',revision='2e1fd397ee46e1388853d2af2c993145b0f1098a',local_files_only=True)
    rows=[]
    for name,attempt in [('oauthlib',None),('iniconfig','attempt-2'),('funcy',None)]:
        base=root/f'data/audits/{name}-replay-20261025'
        evidence=base/attempt if attempt else base
        task=json.loads((base/'task.json').read_text())
        replay=json.loads((evidence/'evidence/report.json').read_text())
        container=f'svaga-{name}-replay-20261025'+('-attempt2' if attempt else '')
        def docker(*args):
            result=subprocess.run(['docker',*args],capture_output=True,text=True,encoding='utf-8',timeout=120)
            if result.returncode:raise RuntimeError(result.stdout+'\n'+result.stderr)
            return result.stdout
        def git(*args):return docker('exec',container,'git','-C','/testbed',*args)
        docker('start',container)
        applied=False
        try:
            assert not git('diff','--name-only').strip()
            git('apply','--check','/tmp/svaga-replay/bug.patch')
            git('apply','/tmp/svaga-replay/bug.patch');applied=True
            patch=git('diff','--reverse','--binary')
            assert patch.strip()
            files=[]
            for path in replay['verified_pre_bug_blobs']:
                code=docker('exec',container,'cat','/testbed/'+path)
                files.append({'path':path,'buggy_code':code,'sha256':hashlib.sha256(code.encode()).hexdigest()})
            prompt='Repair the software issue below. Return a unified diff only. The supplied files are in the buggy state.\n\nISSUE:\n'+task['problem_statement']
            for file in files:prompt+='\n\nFILE: '+file['path']+'\n'+file['buggy_code']
            messages=[{'role':'user','content':prompt},{'role':'assistant','content':patch}]
            full=tokenizer.apply_chat_template(messages,tokenize=True,return_dict=True)['input_ids']
            prefix=tokenizer.apply_chat_template(messages[:1],tokenize=True,return_dict=True,add_generation_prompt=True)['input_ids']
            assert full[:len(prefix)]==prefix
            row={'instance_id':task['instance_id'],'repo':task['repo'],'messages':messages,'files':files,
                 'tokens':{'total':len(full),'target':len(full)-len(prefix)},
                 'local_replay_verified':True,'verification_scope':'listed official tests for clean/buggy/reversed-patch states',
                 'evidence_report':str((evidence/'evidence/report.json').relative_to(root)),
                 'split':'development_only_already_inspected','training_approved':False,
                 'external_benchmark_overlap_cleared':False,'context':'full touched files; file locations selected using known patch paths',
                 'task_source_revision':'77cab9055d42ab4a5c25c89a8f937096db13558e'}
            rows.append(row)
            print(name,row['tokens'],flush=True)
        finally:
            if applied:git('apply','--reverse','/tmp/svaga-replay/bug.patch')
            docker('stop',container)
    with (out/'development-pairs.jsonl').open('w',encoding='utf-8') as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    report={'status':'three_verified_development_pairs_not_10k_training_release',
            'records':len(rows),'fits':{str(n):sum(r['tokens']['total']<=n for r in rows) for n in [4096,8192,16384]},
            'tasks':[{'instance_id':r['instance_id'],'tokens':r['tokens']} for r in rows],
            'tokenizer':'Qwen/Qwen2.5-Coder-1.5B-Instruct','revision':'2e1fd397ee46e1388853d2af2c993145b0f1098a',
            'limitations':['Three deliberately selected development tasks, not a representative dataset.',
                           'Inputs use known patch file locations: oracle localization, not end-to-end repository search.',
                           'Input excludes clean source and bug-introducing diff; target is the reverse repair diff.',
                           'Local replay verification covers the supplied tests, not all possible behavior.',
                           'No training/validation release split assigned and no external benchmark overlap clearance.',
                           'Token limits assessed without truncating full files.']}
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
