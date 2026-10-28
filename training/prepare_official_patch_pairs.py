"""Prepare localized repair candidates from official bug-introducing patches.

Input contains only task text and post-bug hunk code. Output is the reverse diff.
No code is executed; official test metadata is provenance, not local verification.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import pyarrow.parquet as pq
from huggingface_hub import HfApi, hf_hub_download
from transformers import AutoTokenizer
from audit_benchmark_overlap import make_index, screen
from audit_task_title_overlap import title_of

DATASET='SWE-bench/SWE-smith-py'
REVISION='77cab9055d42ab4a5c25c89a8f937096db13558e'


def norm(s):return re.sub(r'\W+',' ',s).strip().casefold()
def sha(s):return hashlib.sha256(s.encode()).hexdigest()


def convert(patch):
    """Validate hunk counts and return buggy excerpts plus reversed diff."""
    lines=patch.splitlines(keepends=True);reverse=[];excerpts=[];path=None;i=0
    while i<len(lines):
        line=lines[i]
        if line.startswith('diff --git '):
            m=re.fullmatch(r'diff --git a/(\S+) b/(\S+)\n?',line)
            if not m or m[1]!=m[2]:raise ValueError('unsupported_path_or_rename')
            path=m[1]
            if not path.endswith('.py') or path.startswith('/') or '..' in path.split('/') or re.search(r'(^|/)(tests?|testing)(/|$)|(^|/)test_',path):raise ValueError('not_python_source_only')
            reverse.append(line)
        elif line.startswith('index '):
            m=re.fullmatch(r'index ([a-f0-9]+)\.\.([a-f0-9]+)(.*?)(\n?)',line)
            if not m:raise ValueError('bad_index')
            reverse.append('index '+m[2]+'..'+m[1]+m[3]+m[4])
        elif line.startswith('--- a/'):reverse.append('--- a/'+path+'\n')
        elif line.startswith('+++ b/'):reverse.append('+++ b/'+path+'\n')
        elif line.startswith('@@ '):
            m=re.fullmatch(r'@@ -(\d+)(,\d+)? \+(\d+)(,\d+)? @@(.*?)(\n?)',line)
            if not m or path is None:raise ValueError('bad_hunk_header')
            reverse.append(f'@@ -{m[3]}{m[4] or ""} +{m[1]}{m[2] or ""} @@{m[5]}{m[6]}')
            old_count=int(m[2][1:]) if m[2] else 1;new_count=int(m[4][1:]) if m[4] else 1
            old_seen=new_seen=0;buggy=[];clean=[];i+=1
            while i<len(lines) and not lines[i].startswith(('@@ ','diff --git ')):
                body=lines[i]
                if body.startswith(' '):old_seen+=1;new_seen+=1;buggy.append(body[1:]);clean.append(body[1:]);reverse.append(body)
                elif body.startswith('-'):old_seen+=1;clean.append(body[1:]);reverse.append('+'+body[1:])
                elif body.startswith('+'):new_seen+=1;buggy.append(body[1:]);reverse.append('-'+body[1:])
                elif body.startswith('\\ No newline'):raise ValueError('no_newline_marker_requires_review')
                else:raise ValueError('unsupported_hunk_line')
                i+=1
            if (old_seen,new_seen)!=(old_count,new_count):raise ValueError('hunk_count_mismatch')
            if buggy==clean:raise ValueError('unchanged_hunk')
            excerpts.append({'path':path,'start_line':int(m[3]),'code':''.join(buggy)})
            continue
        else:raise ValueError('unsupported_patch_metadata')
        i+=1
    if not excerpts:raise ValueError('no_hunks')
    return excerpts,''.join(reverse)


def main():
    root=Path(__file__).resolve().parents[1]
    out=root/'data/prepared/swesmith-localized-10k-candidates-v1'
    if out.exists():raise ValueError('Output exists')
    out.mkdir(parents=True)
    audit_root=root/'data/audits/terminal-bench-2-1-overlap-10k'
    instructions=json.loads((audit_root/'benchmark-instructions.audit-only.json').read_text(encoding='utf-8'))
    benchmark_report=json.loads((audit_root/'report.json').read_text())
    assert all(sha(v)==benchmark_report['instruction_sha256'][k] for k,v in instructions.items())
    sets,index=make_index(instructions)
    old_validation_titles=set()
    with (root/'data/prepared/openthoughts-expanded-10k-v1/full.validation.jsonl').open(encoding='utf-8') as f:
        for line in f:
            title=title_of(json.loads(line))
            if title:old_validation_titles.add(title)
    tokenizer=AutoTokenizer.from_pretrained('Qwen/Qwen2.5-Coder-1.5B-Instruct',revision='2e1fd397ee46e1388853d2af2c993145b0f1098a',local_files_only=True)
    names=sorted(n for n in HfApi().list_repo_files(DATASET,repo_type='dataset',revision=REVISION) if n.startswith('data/train-') and n.endswith('.parquet'))
    counts=Counter();seen_titles=set();seen_patches=set();seen_inputs=set();seen_tasks=set();shards=[]
    selected={'train':0,'validation':0};targets={'train':10000,'validation':1000}
    # Repositories already inspected remain development-validation, never training.
    development_repos=('oauthlib__oauthlib','pytest-dev__iniconfig','Suor__funcy')
    handles={s:(out/f'{s}.candidates.jsonl').open('w',encoding='utf-8') for s in targets}
    try:
        with (out/'exclusions.audit-only.jsonl').open('w',encoding='utf-8') as audit:
            for name in names:
                print('Download/scan',name,flush=True)
                path=hf_hub_download(DATASET,name,repo_type='dataset',revision=REVISION)
                with open(path,'rb') as f:shards.append({'file':name,'sha256':hashlib.file_digest(f,'sha256').hexdigest()})
                for batch in pq.ParquetFile(path).iter_batches(batch_size=32):
                    for row in batch.to_pylist():
                        counts['scanned']+=1;reason=None
                        statement=(row.get('problem_statement') or '').strip();title=norm(statement.splitlines()[0]) if statement else ''
                        patch_hash=sha(row.get('patch') or '')
                        repo=row['repo'];repo_key=repo.split('/')[-1].rsplit('.',1)[0]
                        split='validation' if any(x in repo for x in development_repos) or int(sha('svaga-repo-v1:'+repo_key)[:8],16)%10==0 else 'train'
                        if not statement or not row.get('FAIL_TO_PASS') or not row.get('PASS_TO_PASS'):reason='missing_statement_or_test_evidence'
                        if not reason and title in old_validation_titles:reason='prior_validation_title_overlap'
                        if not reason and (title in seen_titles or patch_hash in seen_patches or row['instance_id'] in seen_tasks):reason='duplicate_title_patch_or_task'
                        if not reason:
                            matches,_=screen({'instruction':statement,'task':row['instance_id']},sets,index)
                            if matches:reason='terminal_bench_instruction_overlap'
                        if not reason:
                            try:excerpts,repair=convert(row['patch'])
                            except ValueError as e:reason=str(e)
                        if not reason:
                            input_hash=sha(json.dumps(excerpts,sort_keys=True))
                            if input_hash in seen_inputs:reason='duplicate_buggy_excerpts'
                        if not reason and selected[split]>=targets[split]:reason='split_quota_met'
                        if not reason:
                            prompt='Repair the issue using the supplied buggy source excerpts. Return a unified diff only. Excerpts are localized using the known bug patch; repository search is outside this task.\n\nISSUE:\n'+statement
                            for excerpt in excerpts:prompt+=f'\n\nFILE: {excerpt["path"]}\nSTART LINE: {excerpt["start_line"]}\n'+excerpt['code']
                            messages=[{'role':'user','content':prompt},{'role':'assistant','content':repair}]
                            ids=tokenizer.apply_chat_template(messages,tokenize=True,return_dict=True)['input_ids']
                            prefix=tokenizer.apply_chat_template(messages[:1],tokenize=True,return_dict=True,add_generation_prompt=True)['input_ids']
                            assert ids[:len(prefix)]==prefix and len(ids)>len(prefix)
                            if len(ids)>4096:reason='over_4096'
                        if reason:
                            counts[reason]+=1;audit.write(json.dumps({'instance_id':row['instance_id'],'split':split,'reason':reason})+'\n');continue
                        item={'instance_id':row['instance_id'],'repo':repo,'source_split':split,'messages':messages,
                              'tokens':{'total':len(ids),'target':len(ids)-len(prefix)},'localization':'oracle_bug_patch_hunks',
                              'bug_patch_sha256':patch_hash,'buggy_excerpts_sha256':input_hash,'image_name':row['image_name'],
                              'upstream_FAIL_TO_PASS_count':len(row['FAIL_TO_PASS']),'upstream_PASS_TO_PASS_count':len(row['PASS_TO_PASS']),
                              'locally_replayed':False,'training_approved':False,'source_dataset':DATASET,'source_revision':REVISION}
                        handles[split].write(json.dumps(item,ensure_ascii=False)+'\n');selected[split]+=1
                        seen_titles.add(title);seen_patches.add(patch_hash);seen_inputs.add(input_hash);seen_tasks.add(row['instance_id'])
                print('Selected',selected,'scanned',counts['scanned'],flush=True)
    finally:
        for f in handles.values():f.close()
    report={'dataset':DATASET,'revision':REVISION,'targets':targets,'selected':selected,'counts':dict(counts),'shards':shards,
            'status':'localized_repair_candidates_not_training_release','max_tokens':4096,
            'tokenizer':'Qwen/Qwen2.5-Coder-1.5B-Instruct','tokenizer_revision':'2e1fd397ee46e1388853d2af2c993145b0f1098a',
            'benchmark_instruction_revision':benchmark_report['benchmark_revision'],
            'limitations':['Localized excerpts, not complete files or apps; context adequacy needs review.',
                           'Repair targets reverse upstream bug patches; individual records not replayed locally.',
                           'Source-order quota sampling; not representative or category-balanced.',
                           'Repository separation and exact title/patch/input deduplication; semantic duplicates may remain.',
                           'Prior validation checked by normalized title; cross-source identifier mapping remains incomplete.',
                           'Terminal-Bench instruction heuristic only, not full contamination clearance.',
                           'Development repositories reserved to validation; no independent final test set claimed.',
                           'No dataset commands executed and no model training performed.']}
    report['output_sha256']={}
    for p in out.glob('*.jsonl'):
        with p.open('rb') as f:report['output_sha256'][p.name]=hashlib.file_digest(f,'sha256').hexdigest()
    (out/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['status','selected','counts']},indent=2))


if __name__=='__main__':main()
