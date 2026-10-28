"""Resume an interrupted frozen repair comparison without changing its evaluator."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid
try:
    from .run_repair_eval import validate_predictions, docker, run_one, summarize
    from .repair_eval_common import sha
except ImportError:
    from run_repair_eval import validate_predictions, docker, run_one, summarize
    from repair_eval_common import sha


def load_resume(root, packet, predictions, run_dir):
    manifest, tasks, records = validate_predictions(packet, predictions)
    provenance = json.loads((run_dir/'run_provenance.json').read_text(encoding='utf-8'))
    if provenance['protocol_version'] != 'repair-dev20-execution-v2' or provenance['tasks_requested'] != 20:
        raise ValueError('Resume supports the complete frozen v2 comparison only')
    for name, expected in provenance['evaluator_sources_sha256'].items():
        if sha((root/'training'/name).read_bytes()) != expected:
            raise ValueError('Evaluator changed since original run: ' + name)
    if sha(predictions.read_bytes()) != provenance['predictions_sha256']:
        raise ValueError('Prediction file changed')
    if sha((run_dir/'generation_results.json').read_bytes()) != provenance['predictions_sha256']:
        raise ValueError('Saved original predictions changed')
    expected_manifest = provenance['packet_manifest_sha256']
    if (sha((packet/'public/manifest.json').read_bytes()) != expected_manifest
            or sha((run_dir/'packet_manifest.json').read_bytes()) != expected_manifest):
        raise ValueError('Frozen task packet changed')
    reports = json.loads((run_dir/'reports.json').read_text(encoding='utf-8'))
    allowed = {(task['instance_id'], variant) for task in tasks for variant in manifest['variants']}
    completed = {(row['instance_id'], row['variant']) for row in reports}
    if len(completed) != len(reports) or not completed <= allowed:
        raise ValueError('Duplicate or unexpected saved results')
    return manifest, tasks, records, reports, completed


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.resume-tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(path)


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, default=root/'results/repair_eval/repair-dev20-full-v2-20261025')
    parser.add_argument('--packet', type=Path, default=root/'data/evaluation/repair-dev20-v1')
    parser.add_argument('--predictions', type=Path, default=root/'results/repair_eval_inputs/repair-dev20-v1/generation_results.json')
    parser.add_argument('--pull-missing', action='store_true')
    args = parser.parse_args()
    manifest, tasks, records, reports, completed = load_resume(root, args.packet, args.predictions, args.run_dir)
    print('Verified existing evaluator, task packet, predictions and', len(reports), 'saved variant results.', flush=True)
    if len(completed) == len(tasks)*len(manifest['variants']):
        print('All 40 results already saved; no tests repeated.'); return
    docker('info', '--format', '{{.ServerVersion}}')
    tag = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
    backup = args.run_dir/('reports-before-resume-' + tag + '.json')
    backup.write_bytes((args.run_dir/'reports.json').read_bytes())
    event = {'started_utc': datetime.now(timezone.utc).isoformat(), 'resume_id': tag,
             'saved_results_before_resume': len(reports), 'backup': backup.name,
             'resume_script_sha256': sha(Path(__file__).read_bytes()),
             'evaluator_protocol_unchanged': 'repair-dev20-execution-v2'}
    (args.run_dir/('resume-' + tag + '.json')).write_text(json.dumps(event, indent=2), encoding='utf-8')
    for index, task in enumerate(tasks, 1):
        for variant in manifest['variants']:
            key = (task['instance_id'], variant)
            if key in completed:
                continue
            attempt = args.run_dir/(sha(task['instance_id'])[:16] + '-' + variant + '-resume-' + tag)
            row = run_one(root, task, records[key], attempt, args.pull_missing)
            row['attempt_directory'] = str(attempt.relative_to(args.run_dir))
            reports.append(row); completed.add(key)
            atomic_json(args.run_dir/'reports.json', reports)
            atomic_json(args.run_dir/'summary.json', summarize(reports, len(tasks)))
            print(index, '/', len(tasks), variant, task['instance_id'], row['status'],
                  '| saved', len(reports), '/40', flush=True)
    event['completed_utc'] = datetime.now(timezone.utc).isoformat()
    event['saved_results_after_resume'] = len(reports)
    atomic_json(args.run_dir/('resume-' + tag + '.json'), event)
    print('Comparison finished:', args.run_dir/'summary.json', flush=True)


if __name__ == '__main__':
    main()
