"""Download pinned tool-format shards; audit source labels, never execute traces."""
import json
from collections import Counter
from pathlib import Path
import hashlib
import pyarrow.parquet as pq
from huggingface_hub import HfApi, hf_hub_download

DATASET = 'SWE-bench/SWE-smith-trajectories'
REVISION = '08e109b4a59eaeebf80e4675cd125d42e7ac99a4'

def main():
    root = Path(__file__).resolve().parents[1]
    out = root/'data/samples/swesmith-official-complete-audit-v1'
    out.mkdir(exist_ok=True)
    if (out/'report.json').exists():
        raise ValueError('Audit already completed; refusing overwrite')
    names = sorted(n for n in HfApi().list_repo_files(DATASET,repo_type='dataset',revision=REVISION)
                   if n.startswith('data/tool-') and n.endswith('.parquet'))
    assert names, 'No tool shards'
    counts, instances, resolved_instances, trajectories = Counter(), set(), set(), set()
    patches, sample, shards = set(), [], []
    for name in names:
        print('Downloading',name,flush=True)
        path = hf_hub_download(DATASET,name,repo_type='dataset',revision=REVISION)
        with open(path,'rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
        shards.append({'file':name,'sha256':digest})
        parquet=pq.ParquetFile(path)
        for batch in parquet.iter_batches(batch_size=32):
            for row in batch.to_pylist():
                counts['rows']+=1
                counts['resolved' if row['resolved'] is True else 'not_resolved']+=1
                instances.add(row['instance_id']);trajectories.add(row['traj_id'])
                if row['resolved'] is True:
                    resolved_instances.add(row['instance_id'])
                    patches.add(hashlib.sha256((row['patch'] or '').encode()).hexdigest())
                    if len(sample)<100: sample.append(row)
        print('Scanned',counts['rows'],'resolved tasks',len(resolved_instances),flush=True)
        (out/'progress.json').write_text(json.dumps({'counts':dict(counts),'completed_shards':shards},indent=2),encoding='utf-8')
    with (out/'resolved-first100.audit-only.jsonl').open('w',encoding='utf-8') as f:
        for row in sample:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    (out/'resolved-instance-ids.json').write_text(json.dumps(sorted(resolved_instances)),encoding='utf-8')
    report={'dataset':DATASET,'revision':REVISION,'format':'tool','counts':dict(counts),
            'unique_instances':len(instances),'unique_resolved_instances':len(resolved_instances),
            'unique_trajectory_ids':len(trajectories),'unique_resolved_patch_hashes':len(patches),
            'shards':shards,'status':'upstream_labels_only_not_training_ready',
            'limitations':['Resolved is an upstream label, not local replay verification.',
                           'Only one format scanned; do not add xml/ticks counts as distinct tasks.',
                           'First 100 resolved trajectories saved for length and provenance inspection; not representative.',
                           'Cross-source validation and benchmark overlap not cleared.']}
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
