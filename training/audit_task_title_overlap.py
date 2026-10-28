"""Flag identical normalized task titles across splits; not semantic clearance."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re


def title_of(row):
    text = row['messages'][0]['content']
    if 'Task Description:' not in text:
        return None
    text = text.split('Task Description:', 1)[1].strip()
    if not text:
        return None
    return re.sub(r'\W+', ' ', text.splitlines()[0]).strip().casefold()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; no overwrite')
    titles = {s: defaultdict(list) for s in ('train', 'validation')}
    missing = {}
    hashes = {}
    for split in titles:
        missing[split] = 0
        h = hashlib.sha256()
        with (args.source_dir / f'full.{split}.jsonl').open('rb') as f:
            for line in f:
                h.update(line)
                if not line.strip():
                    continue
                row = json.loads(line)
                title = title_of(row)
                if title:
                    titles[split][title].append(row['task'])
                else:
                    missing[split] += 1
        hashes[split] = h.hexdigest()
    matches = [{'title': title, 'train': titles['train'][title],
                'validation': titles['validation'][title]}
               for title in sorted(titles['train'].keys() & titles['validation'].keys())]
    report = {'status': 'overlap_candidates_require_review',
        'source_sha256': hashes, 'shared_title_count': len(matches),
        'affected_train_records': sum(len(m['train']) for m in matches),
        'affected_validation_records': sum(len(m['validation']) for m in matches),
        'missing_titles': missing, 'matches': matches,
        'limitations': ['Same title is a flag, not automatically an identical task.',
            'Different titles can still describe the same bug; this is not semantic clearance.',
            'No split changes, model training or dataset commands executed.']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='matches'}, indent=2))


if __name__ == '__main__':
    main()
