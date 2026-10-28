"""Build repository-balanced repair candidates from verified buggy source files.

Downloads are treated as text only. Original files must match official pre-bug
Git blobs; literal patch application must match post-bug blobs. Context includes
whole affected functions, class scaffolding, and referenced module definitions.
This is conservative static context expansion, not semantic completeness proof.
"""
import ast
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote
from urllib.request import Request, urlopen
import pyarrow.parquet as pq
from huggingface_hub import snapshot_download
from transformers import AutoTokenizer
from prepare_official_patch_pairs import convert, norm, sha, DATASET, REVISION
from package_official_10k import normalized_diff
from audit_benchmark_overlap import make_index, screen
from audit_task_title_overlap import title_of


def blob(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def patch_files(patch):
    convert(patch)  # Reject unsupported headers and invalid hunk lengths first.
    result=[]
    for section in patch.split('diff --git ')[1:]:
        lines=section.splitlines(keepends=True)
        path=re.match(r'a/(\S+) b/',lines[0])[1]
        old,new=re.match(r'index ([a-f0-9]+)\.\.([a-f0-9]+)',lines[1]).groups()
        hunks=[];i=4
        while i<len(lines):
            match=re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',lines[i])
            if not match:raise ValueError('unexpected_hunk')
            start=int(match[1])-1;new_start=int(match[3])-1;i+=1;before=[];after=[];changed=[];cursor=new_start
            while i<len(lines) and not lines[i].startswith('@@ '):
                line=lines[i]
                if line[0] in ' -':before.append(line[1:])
                if line[0] in ' +':
                    after.append(line[1:])
                    if line[0]=='+':changed.append(cursor+1)
                    cursor+=1
                elif line[0]=='-':changed.append(cursor+1)
                i+=1
            hunks.append((start,before,after,changed))
        result.append({'path':path,'old':old,'new':new,'hunks':hunks})
    return result


def apply_bug(clean,info):
    lines=clean.splitlines(keepends=True);delta=0;changed=[]
    for start,before,after,positions in info['hunks']:
        start+=delta
        if lines[start:start+len(before)]!=before:raise ValueError('patch_context_mismatch')
        lines[start:start+len(before)]=after;delta+=len(after)-len(before);changed.extend(positions)
    buggy=''.join(lines)
    if not blob(buggy.encode()).startswith(info['new']):raise ValueError('post_bug_blob_mismatch')
    return buggy,changed


def context_blocks(buggy,changed):
    tree=ast.parse(buggy);lines=buggy.splitlines(keepends=True);nodes=list(ast.walk(tree))
    selected={};parents={child:parent for parent in nodes for child in ast.iter_child_nodes(parent)}
    function_nodes=[n for n in nodes if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
    load_names=[n for n in nodes if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load)]
    top={}
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            top[node.name]=node
        elif isinstance(node,(ast.Import,ast.ImportFrom)):
            for alias in node.names:top[alias.asname or alias.name.split('.')[0]]=node
        elif isinstance(node,(ast.Assign,ast.AnnAssign)):
            for sub in ast.walk(node):
                if isinstance(sub,ast.Name) and isinstance(sub.ctx,ast.Store):top[sub.id]=node
    def add(node):
        start=min([node.lineno]+[d.lineno for d in getattr(node,'decorator_list',[])])
        selected[(start,node.end_lineno)]=''.join(lines[start-1:node.end_lineno])
    for position in changed:
        position=max(1,min(position,len(lines)))
        functions=[n for n in function_nodes if n.lineno<=position<=n.end_lineno]
        if functions:
            node=max(functions,key=lambda n:n.end_lineno-n.lineno)
            # Include an enclosing function when a closure is modified.
            while isinstance(parents.get(node),(ast.FunctionDef,ast.AsyncFunctionDef)):node=parents[node]
            add(node)
            ancestor=parents.get(node)
            if isinstance(ancestor,ast.ClassDef):
                body_start=ancestor.body[0].lineno
                selected[(ancestor.lineno,body_start-1)]=''.join(lines[ancestor.lineno-1:body_start-1])
                for member in ancestor.body:
                    if isinstance(member,(ast.Assign,ast.AnnAssign)) or isinstance(member,(ast.FunctionDef,ast.AsyncFunctionDef)) and member.name in ('__init__','__new__'):add(member)
        else:
            nodes=[n for n in tree.body if n.lineno<=position<=n.end_lineno]
            if not nodes:raise ValueError('changed_line_context_unresolved')
            add(nodes[0])
    # Conservatively follow referenced names into module definitions/imports.
    for _ in range(8):
        needed=set()
        for start,end in list(selected):
            for node in load_names:
                if start<=node.lineno<=end:needed.add(node.id)
        before=len(selected)
        for name in needed:
            if name in top:add(top[name])
        if len(selected)==before:break
    else:raise ValueError('context_dependency_expansion_limit')
    # Merge overlapping ranges so code is never duplicated or silently cut.
    ranges=[]
    for start,end in sorted(selected):
        if ranges and start<=ranges[-1][1]+1:ranges[-1][1]=max(ranges[-1][1],end)
        else:ranges.append([start,end])
    return [{'start_line':start,'end_line':end,'code':''.join(lines[start-1:end])} for start,end in ranges]


def main():
    root=Path(__file__).resolve().parents[1]
    out=root/'data/prepared/swesmith-context-enriched-candidates-v2'
    if out.exists():raise ValueError('Output exists')
    out.mkdir(parents=True)
    cache=root/'data/source-cache/swesmith-blob-files';cache.mkdir(parents=True,exist_ok=True)
    instructions=json.loads((root/'data/audits/terminal-bench-2-1-overlap-10k/benchmark-instructions.audit-only.json').read_text(encoding='utf-8'))
    sets,index=make_index(instructions)
    prior_titles=set()
    with (root/'data/prepared/openthoughts-expanded-10k-v1/full.validation.jsonl').open(encoding='utf-8') as f:
        for line in f:
            title=title_of(json.loads(line))
            if title:prior_titles.add(title)
    snapshot=Path(snapshot_download(DATASET,repo_type='dataset',revision=REVISION,local_files_only=True))
    queues=defaultdict(list);counts=Counter()
    for path in sorted(snapshot.glob('data/train-*.parquet')):
        for batch in pq.ParquetFile(path).iter_batches(batch_size=32):
            for row in batch.to_pylist():
                counts['source_rows']+=1
                if not all(row.get(k) for k in ['problem_statement','FAIL_TO_PASS','PASS_TO_PASS']):counts['missing_evidence']+=1;continue
                title=norm(row['problem_statement'].strip().splitlines()[0])
                if title in prior_titles:counts['prior_validation_title']+=1;continue
                if screen({'instruction':row['problem_statement'],'task':row['instance_id']},sets,index)[0]:counts['benchmark_overlap_flag']+=1;continue
                try:row['_files']=patch_files(row['patch'])
                except ValueError:counts['unsupported_patch']+=1;continue
                row['_title']=title;queues[row['repo']].append(row)
    queues={repo:deque(sorted(rows,key=lambda r:sha(r['instance_id']))) for repo,rows in sorted(queues.items(),key=lambda x:sha(x[0]))}
    development=('oauthlib__oauthlib','pytest-dev__iniconfig','Suor__funcy')
    def split_for(repo):
        key=repo.split('/')[-1].rsplit('.',1)[0]
        return 'validation' if any(x in repo for x in development) or int(sha('svaga-repo-v1:'+key)[:8],16)%10==0 else 'train'
    tokenizer=AutoTokenizer.from_pretrained('Qwen/Qwen2.5-Coder-1.5B-Instruct',revision='2e1fd397ee46e1388853d2af2c993145b0f1098a',local_files_only=True)
    totals=Counter();per_repo=Counter();seen_titles=set();seen_patches=set();seen_inputs=set();fail_cache={}
    targets={'train':10000,'validation':1000};caps={'train':400,'validation':150}
    def fetch(repo,info):
        key=sha(repo+':'+info['path']+':'+info['old']);dest=cache/(key+'.bin')
        if key in fail_cache:raise ValueError(fail_cache[key])
        try:
            if dest.exists():data=dest.read_bytes()
            else:
                url='https://raw.githubusercontent.com/'+repo+'/main/'+quote(info['path'])
                with urlopen(Request(url,headers={'User-Agent':'SVAGA-context-audit'}),timeout=20) as response:data=response.read()
                if len(data)>3_000_000:raise ValueError('source_file_too_large')
                if not blob(data).startswith(info['old']):raise ValueError('pre_bug_blob_mismatch')
                dest.write_bytes(data)
            if not blob(data).startswith(info['old']):raise ValueError('cached_pre_bug_blob_mismatch')
            return data.decode('utf-8'),{'path':info['path'],'clean_git_blob':blob(data),'clean_file_sha256':hashlib.sha256(data).hexdigest(),'cache_key':key}
        except Exception as error:
            reason=type(error).__name__+':'+str(error)[:100];fail_cache[key]=reason;raise ValueError(reason)
    streams={s:(out/f'{s}.candidates.jsonl').open('w',encoding='utf-8') for s in targets}
    try:
        with (out/'exclusions.audit-only.jsonl').open('w',encoding='utf-8') as audit,ThreadPoolExecutor(max_workers=6) as pool:
            round_number=0
            while True:
                work=[]
                for repo,queue in queues.items():
                    split=split_for(repo)
                    if queue and totals[split]<targets[split] and per_repo[repo]<caps[split]:work.append(queue.popleft())
                if not work:break
                round_number+=1
                requests={(r['repo'],f['path'],f['old']):(r['repo'],f) for r in work for f in r['_files']}
                futures={k:pool.submit(fetch,*v) for k,v in requests.items()}
                fetched={}
                for key,future in futures.items():
                    try:fetched[key]=future.result()
                    except ValueError as e:fetched[key]=str(e)
                for row in work:
                    repo=row['repo'];split=split_for(repo);patch_hash=sha(row['patch']);reason=None
                    if row['_title'] in seen_titles or patch_hash in seen_patches:reason='duplicate_title_or_patch'
                    try:
                        if reason:raise ValueError(reason)
                        files=[];provenance=[]
                        for info in row['_files']:
                            result=fetched[(repo,info['path'],info['old'])]
                            if isinstance(result,str):raise ValueError('source_fetch_or_blob_failure:'+result)
                            clean,origin=result;buggy,changed=apply_bug(clean,info)
                            blocks=context_blocks(buggy,changed)
                            files.append({'path':info['path'],'blocks':blocks})
                            provenance.append({**origin,'buggy_git_blob':blob(buggy.encode())})
                        input_hash=sha(json.dumps(files,sort_keys=True))
                        if input_hash in seen_inputs:raise ValueError('duplicate_buggy_context')
                        _,repair=convert(row['patch']);target=normalized_diff(repair)
                        prompt='Repair the issue using the supplied buggy Python source context. Return a unified diff only. Affected file locations are supplied; repository search is outside this task.\n\nISSUE:\n'+row['problem_statement']
                        for file in files:
                            for block in file['blocks']:prompt+=f'\n\nFILE: {file["path"]}\nLINES: {block["start_line"]}-{block["end_line"]}\n'+block['code']
                        messages=[{'role':'user','content':prompt},{'role':'assistant','content':target}]
                        full=tokenizer.apply_chat_template(messages,tokenize=True,return_dict=True)['input_ids']
                        prefix=tokenizer.apply_chat_template(messages[:1],tokenize=True,return_dict=True,add_generation_prompt=True)['input_ids']
                        assert full[:len(prefix)]==prefix and len(full)>len(prefix)
                        if len(full)>4096:raise ValueError('enriched_context_over_4096')
                        if totals[split]>=targets[split]:raise ValueError('quota_met')
                        item={'instance_id':row['instance_id'],'repo':repo,'source_split':split,'messages':messages,'tokens':{'total':len(full),'target':len(full)-len(prefix)},
                              'source_provenance':provenance,'context_files':files,'bug_patch_sha256':patch_hash,'buggy_excerpts_sha256':input_hash,
                              'source_revision':REVISION,'image_name':row['image_name'],'upstream_FAIL_TO_PASS_count':len(row['FAIL_TO_PASS']),
                              'upstream_PASS_TO_PASS_count':len(row['PASS_TO_PASS']),'locally_replayed':False,'training_approved':False,
                              'context_method':'whole_affected_functions_class_scaffolding_referenced_module_definitions',
                              'context_semantically_complete':False}
                        streams[split].write(json.dumps(item,ensure_ascii=False)+'\n');totals[split]+=1;per_repo[repo]+=1
                        seen_titles.add(row['_title']);seen_patches.add(patch_hash);seen_inputs.add(input_hash)
                    except (ValueError,SyntaxError,UnicodeError,RecursionError) as error:
                        reason=str(error);category=reason.split(':')[0]
                        counts[category]+=1;audit.write(json.dumps({'instance_id':row['instance_id'],'reason':reason})+'\n')
                if round_number%10==0:print('Round',round_number,'selected',dict(totals),'repos',len(per_repo),flush=True)
    finally:
        for stream in streams.values():stream.close()
    report={'status':'context_enriched_candidates_not_training_release','source_dataset':DATASET,'source_revision':REVISION,
            'targets':targets,'selected':dict(totals),'per_repository_caps':caps,'repository_counts':dict(per_repo),'counts':dict(counts),
            'tokenizer':'Qwen/Qwen2.5-Coder-1.5B-Instruct','tokenizer_revision':'2e1fd397ee46e1388853d2af2c993145b0f1098a','max_tokens':4096,
            'limitations':['Whole affected functions and statically referenced module definitions improve context but cannot prove semantic sufficiency.',
                           'Buggy file locations are known from patches; oracle localization remains.',
                           'Some helpers accessed through object attributes or dynamic imports can remain outside supplied context.',
                           'Source files verified against official Git blob prefixes, not executed.',
                           'Repository-separated balanced round-robin selection; mutation/category balance not enforced.',
                           'Upstream test evidence retained; new records have not been replayed locally.',
                           'Benchmark/prior-validation overlap screening remains heuristic.']}
    report['files_sha256']={}
    for p in out.glob('*.jsonl'):
        with p.open('rb') as f:report['files_sha256'][p.name]=hashlib.file_digest(f,'sha256').hexdigest()
    (out/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'selected':dict(totals),'counts':dict(counts)},indent=2))


if __name__=='__main__':main()
