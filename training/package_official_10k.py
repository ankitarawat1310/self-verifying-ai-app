"""Package existing candidates for explicit experimental localized repair SFT."""
import hashlib
import json
from pathlib import Path
import re
import zipfile
import argparse
from transformers import AutoTokenizer


def normalized_diff(diff):
    output=[];removed=[];added=[]
    def flush():
        output.extend(removed);output.extend(added);removed.clear();added.clear()
    for line in diff.splitlines(keepends=True):
        if line.startswith('index '):continue
        if line.startswith('@@ '):line=re.sub(r'(@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@).*',r'\1',line)
        if line.startswith('-') and not line.startswith('--- '):removed.append(line)
        elif line.startswith('+') and not line.startswith('+++ '):added.append(line)
        else:flush();output.append(line)
    flush()
    return ''.join(output)


def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir',type=Path,default=root/'data/prepared/swesmith-context-enriched-candidates-v2')
    parser.add_argument('--output-dir',type=Path,default=root/'data/prepared/swesmith-context-repair-10k-v2')
    args=parser.parse_args();source=args.source_dir;out=args.output_dir
    if out.exists():raise ValueError('Package exists')
    manifest=json.loads((source/'manifest.json').read_text())
    report=json.loads((source/'validation-report.json').read_text())
    assert report['cross_split_task_repository_patch_input_overlap']==0
    tokenizer=AutoTokenizer.from_pretrained(manifest['tokenizer'],revision=manifest['tokenizer_revision'],local_files_only=True)
    out.mkdir(parents=True);stats={};hashes={}
    for split,target_count in [('train',10000),('validation',1000)]:
        path=source/f'{split}.candidates.jsonl'
        source_hashes=manifest.get('output_sha256',manifest.get('files_sha256'))
        with path.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==source_hashes[path.name]
        count=0;largest=0;total_targets=0
        with path.open(encoding='utf-8') as inp,(out/f'{split}.jsonl').open('w',encoding='utf-8') as output:
            for line in inp:
                row=json.loads(line);target=normalized_diff(row['messages'][1]['content'])
                assert not any(x.startswith('index ') for x in target.splitlines())
                messages=[row['messages'][0],{'role':'assistant','content':target}]
                if messages==row['messages']:
                    # Source hashes and the pinned tokenizer identity were verified above.
                    tokens=row['tokens']
                    assert 0<tokens['target']<tokens['total']<=4096
                else:
                    full=tokenizer.apply_chat_template(messages,tokenize=True,return_dict=True)['input_ids']
                    prompt=tokenizer.apply_chat_template(messages[:1],tokenize=True,return_dict=True,add_generation_prompt=True)['input_ids']
                    assert full[:len(prompt)]==prompt and len(prompt)<len(full)<=4096
                    tokens={'total':len(full),'target':len(full)-len(prompt)}
                item={**row,'messages':messages,'tokens':tokens,
                      'usage':'experimental_localized_repair_imitation','independently_verified':False}
                output.write(json.dumps(item,ensure_ascii=False)+'\n');count+=1;largest=max(largest,tokens['total']);total_targets+=tokens['target']
        assert count==target_count
        stats[split]={'records':count,'max_tokens':largest,'target_tokens':total_targets}
        with (out/f'{split}.jsonl').open('rb') as f:hashes[f'{split}.jsonl']=hashlib.file_digest(f,'sha256').hexdigest()
        print(split,stats[split],flush=True)
    enriched=manifest.get('status','').startswith('context_enriched')
    package={'status':'experimental_training_package_not_verified_repair_corpus','counts':{'train':10000,'validation':1000},
             'source_dataset':manifest.get('dataset',manifest.get('source_dataset')),'source_revision':manifest.get('revision',manifest.get('source_revision')),
             'source_manifest_sha256':hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest(),
             'tokenizer':manifest['tokenizer'],'tokenizer_revision':manifest['tokenizer_revision'],
             'max_tokens':4096,'statistics':stats,'files_sha256':hashes,
             'target_format':'unified_diff_no_blob_hashes_or_hunk_function_labels_deletions_before_additions',
             'scope':'context-enriched localized Python repair' if enriched else 'localized Python repair; not whole-app generation and not four specialist datasets',
             'context_enriched':enriched,
             'limitations':manifest['limitations']+[
                 'Not a full manual review or proof of semantic context completeness.',
                 'Normalization changes target serialization; earlier adapter is a separate experiment.',
                 'Use development validation for tuning; it is not an untouched final evaluation benchmark.']}
    (out/'manifest.json').write_text(json.dumps(package,indent=2),encoding='utf-8')
    archive=out.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name in ['manifest.json','train.jsonl','validation.jsonl']:z.write(out/name,name)
    print('Package:',archive,'bytes',archive.stat().st_size)


if __name__=='__main__':main()
