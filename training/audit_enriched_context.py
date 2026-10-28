"""Check enriched candidate source identity and context; Git-apply sample targets.

No downloaded Python code, model output, or corpus shell command is executed.
"""
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import pyarrow.parquet as pq
from huggingface_hub import snapshot_download
from enrich_official_context import patch_files, apply_bug, blob
from package_official_10k import normalized_diff
from prepare_official_patch_pairs import DATASET, REVISION, convert, sha


def main():
    root=Path(__file__).resolve().parents[1];out=root/'data/prepared/swesmith-context-enriched-candidates-v2'
    manifest=json.loads((out/'manifest.json').read_text())
    rows={};sets={};stats={}
    for split in ['train','validation']:
        path=out/f'{split}.candidates.jsonl'
        with path.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==manifest['files_sha256'][path.name]
        rows[split]=[json.loads(x) for x in path.open(encoding='utf-8')]
        sets[split]={key:{r[key] for r in rows[split]} for key in ['instance_id','repo','bug_patch_sha256','buggy_excerpts_sha256']}
        assert len(sets[split]['instance_id'])==len(rows[split])
        counts=Counter(r['repo'] for r in rows[split]);n=len(rows[split])
        stats[split]={'records':n,'repositories':len(counts),'largest_repository_count':max(counts.values(),default=0),
                      'largest_repository_share':max(counts.values(),default=0)/n if n else None,
                      'top_three_repository_share':sum(v for _,v in counts.most_common(3))/n if n else None,
                      'max_tokens':max((r['tokens']['total'] for r in rows[split]),default=0),'repository_counts':dict(counts)}
        assert all(0<r['tokens']['target']<r['tokens']['total']<=4096 for r in rows[split])
    for key in sets['train']:assert not sets['train'][key]&sets['validation'][key],key
    byid={r['instance_id']:r for split in rows.values() for r in split}
    snapshot=Path(snapshot_download(DATASET,repo_type='dataset',revision=REVISION,local_files_only=True))
    tasks={}
    for shard in sorted(snapshot.glob('data/train-*.parquet')):
        for batch in pq.ParquetFile(shard).iter_batches(batch_size=32):
            for row in batch.to_pylist():
                if row['instance_id'] in byid:tasks[row['instance_id']]=row
    assert len(tasks)==len(byid)
    @lru_cache(maxsize=32)
    def read_source(key):
        assert re.fullmatch('[a-f0-9]{64}',key)
        return (root/'data/source-cache/swesmith-blob-files'/f'{key}.bin').read_bytes()
    verified=0;blocks_checked=0
    for taskid,row in byid.items():
        task=tasks[taskid]
        assert sha(task['patch'])==row['bug_patch_sha256']
        _,reverse=convert(task['patch'])
        assert normalized_diff(reverse)==row['messages'][1]['content']
        origins={p['path']:p for p in row['source_provenance']}
        context={p['path']:p['blocks'] for p in row['context_files']}
        for info in patch_files(task['patch']):
            origin=origins[info['path']];data=read_source(origin['cache_key'])
            assert blob(data)==origin['clean_git_blob'] and blob(data).startswith(info['old'])
            assert hashlib.sha256(data).hexdigest()==origin['clean_file_sha256']
            buggy,_=apply_bug(data.decode('utf-8'),info)
            assert blob(buggy.encode())==origin['buggy_git_blob']
            lines=buggy.splitlines(keepends=True)
            for block in context[info['path']]:
                assert block['code']==''.join(lines[block['start_line']-1:block['end_line']])
                assert block['code'] in row['messages'][0]['content']
                blocks_checked+=1
        verified+=1
        if verified%2000==0:print('Verified source/context:',verified,flush=True)
    # Distinct-project sample; preserve a readable artifact for subsequent review.
    sample=[]
    for split in ['train','validation']:
        projects={}
        for row in rows[split]:
            key=sha(row['instance_id'])
            if row['repo'] not in projects or key<projects[row['repo']][0]:projects[row['repo']]=(key,row)
        sample.extend(v[1] for _,v in sorted(projects.items(),key=lambda x:sha(x[0]))[:10])
    samples_checked=[]
    for row in sample:
        with tempfile.TemporaryDirectory(prefix='svaga-patch-check-') as td:
            directory=Path(td);task=tasks[row['instance_id']]
            origins={p['path']:p for p in row['source_provenance']}
            for info in patch_files(task['patch']):
                data=read_source(origins[info['path']]['cache_key']);buggy,_=apply_bug(data.decode(),info)
                dest=directory/info['path']
                assert dest.resolve().is_relative_to(directory.resolve())
                dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(buggy.encode())
            patch=directory/'repair.diff';patch.write_text(row['messages'][1]['content'],encoding='utf-8',newline='\n')
            result=subprocess.run(['git','-c','core.autocrlf=false','-c','core.eol=lf','apply',str(patch)],cwd=directory,text=True,capture_output=True)
            assert result.returncode==0,(row['instance_id'],result.stderr)
            for info in patch_files(task['patch']):
                actual=(directory/info['path']).read_bytes()
                if not blob(actual).startswith(info['old']):
                    import difflib
                    expected=read_source(origins[info['path']]['cache_key'])
                    detail={'instance_id':row['instance_id'],'path':info['path'],'expected_blob':blob(expected),'actual_blob':blob(actual),
                            'diff':''.join(difflib.unified_diff(expected.decode().splitlines(True),actual.decode().splitlines(True),fromfile='expected-clean',tofile='actual-repair'))}
                    (out/'sample-patch-mismatch.audit-only.json').write_text(json.dumps(detail,indent=2),encoding='utf-8')
                    raise AssertionError(detail)
        samples_checked.append({'instance_id':row['instance_id'],'repo':row['repo'],'source_split':row['source_split'],'patch_restores_verified_clean_blob':True})
    with (out/'review-sample-20.audit-only.jsonl').open('w',encoding='utf-8') as f:
        for row in sample:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    report={'status':'source_context_and_sample_patch_checks_passed_not_test_execution',
            'splits':stats,'cross_split_task_repository_patch_input_overlap':0,
            'all_records_source_context_verified':verified,'source_blocks_checked':blocks_checked,
            'git_apply_sample_checks':samples_checked,'new_tests_executed':0,
            'git_line_ending_policy':'core.autocrlf=false, core.eol=lf to match official Linux files',
            'limitations':['Git apply checks patch application and restoration, not program behavior.',
                           'All supplied context matches the buggy source; semantic completeness is not proven.',
                           'Existing three-task runtime replay evidence remains separate.',
                           'Dataset targets localized repair only; no spec/test-generation or explicit RAG supervision.']}
    (out/'validation-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['all_records_source_context_verified','source_blocks_checked']},indent=2))
    print('Sample patch application checks:',len(samples_checked))
    print('Split summary:',json.dumps({s:{k:v for k,v in x.items() if k!='repository_counts'} for s,x in stats.items()},indent=2))


if __name__=='__main__':main()
