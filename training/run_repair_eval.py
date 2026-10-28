"""Run frozen generated repairs in fresh Docker containers; no host code execution."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
import uuid
try:
    from .repair_eval_common import sha
except ImportError:
    from repair_eval_common import sha


def docker(*args, timeout=120, check=True):
    result = subprocess.run(['docker', *args], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(result.stderr[-3000:] or result.stdout[-3000:])
    return result


def validate_predictions(packet, predictions):
    manifest_raw = (packet/'public/manifest.json').read_bytes()
    manifest = json.loads(manifest_raw)
    data = json.loads(predictions.read_text(encoding='utf-8-sig'))
    for key, value in [('manifest_sha256', sha(manifest_raw)), ('model', manifest['model']),
                       ('revision', manifest['model_revision']), ('decoding', manifest['decoding']),
                       ('adapter_artifacts_sha256', manifest['adapter_artifacts_sha256'])]:
        if data.get(key) != value:
            raise ValueError('Generation provenance mismatch: ' + key)
    private_raw = (packet/'private_tasks.jsonl').read_bytes()
    assert sha(private_raw) == manifest['private_tasks_sha256']
    tasks = [json.loads(line) for line in private_raw.decode('utf-8').splitlines() if line.strip()]
    public_raw = (packet/'public/prompts.jsonl').read_bytes()
    assert sha(public_raw) == manifest['prompts_sha256']
    prompts = {r['instance_id']: r for r in map(json.loads, public_raw.decode().splitlines())}
    assert len(tasks) == manifest['tasks'] and {t['instance_id'] for t in tasks} == set(prompts)
    records = {}
    for row in data['records']:
        key = (row['instance_id'], row['variant'])
        if key in records or key[0] not in prompts or key[1] not in manifest['variants']:
            raise ValueError('Duplicate or unexpected generated output')
        if row['prompt_sha256'] != prompts[key[0]]['prompt_sha256'] or not isinstance(row['text'], str):
            raise ValueError('Generated output prompt mismatch')
        if not isinstance(row.get('hit_token_limit'), bool):
            raise ValueError('Missing generation-limit flag')
        records[key] = row
    if set(records) != {(t['instance_id'], v) for t in tasks for v in manifest['variants']}:
        raise ValueError('Need all 40 completed generations before execution')
    return manifest, tasks, records


def run_one(root, task, candidate, out, pull_missing):
    report_base = {'instance_id': task['instance_id'], 'variant': candidate['variant'],
                   'environment_valid': False, 'candidate_passed': False}
    inspected = docker('image', 'inspect', task['image_name'], check=False)
    if inspected.returncode and pull_missing:
        print('Downloading official image:', task['image_name'], flush=True)
        try:
            docker('pull', task['image_name'], timeout=3600)
            inspected = docker('image', 'inspect', task['image_name'])
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            return {**report_base, 'status': 'image_download_error', 'image': task['image_name'], 'detail': str(error)}
    if inspected.returncode:
        return {**report_base, 'status': 'image_unavailable', 'image': task['image_name']}
    image = json.loads(inspected.stdout)[0]
    image_id = image['Id']
    name = 'svaga-generated-' + sha(task['instance_id'])[:10] + '-' + candidate['variant'] + '-' + uuid.uuid4().hex[:8]
    out.mkdir(parents=True, exist_ok=False)
    payload = out/'execution-input.json'
    payload.write_text(json.dumps({'task': task, 'candidate': candidate}), encoding='utf-8')
    start = time.perf_counter()
    try:
        docker('run', '--detach', '--name', name, '--network', 'none', '--cpus', '2', '--memory', '4g',
               '--pids-limit', '256', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
               '--entrypoint', '/bin/sh', image_id, '-c', 'sleep infinity')
        interpreter = docker('exec', name, '/bin/sh', '-c',
            'for p in /opt/miniconda3/envs/testbed/bin/python /testbed/.venv/bin/python /opt/venv/bin/python; do if [ -x "$p" ]; then echo "$p"; exit 0; fi; done; command -v python').stdout.strip()
        if not interpreter.startswith('/') or '\n' in interpreter:
            raise ValueError('No unambiguous image Python interpreter')
        for filename in ['repair_eval_common.py', 'repair_eval_container.py']:
            docker('cp', str(root/'training'/filename), name + ':/tmp/' + filename)
        docker('cp', str(payload), name + ':/tmp/svaga-eval-task.json')
        try:
            execution = docker('exec', name, interpreter, '/tmp/repair_eval_container.py', timeout=2600, check=False)
            (out/'container.log').write_text(execution.stdout + '\n' + execution.stderr, encoding='utf-8')
        finally:
            docker('cp', name + ':/tmp/svaga-generated-evaluation', str(out/'evidence'), check=False)
        report_path = out/'evidence/report.json'
        if not report_path.exists():
            raise RuntimeError('Container did not produce a report')
        report = json.loads(report_path.read_text(encoding='utf-8'))
        if report['instance_id'] != task['instance_id'] or report['variant'] != candidate['variant']:
            raise ValueError('Container report identity mismatch')
        report.update(image_id=image_id, image_ref=task['image_name'],
                      image_repo_digests=image.get('RepoDigests', []), execution_seconds=time.perf_counter()-start)
        return report
    except Exception as error:
        return {**report_base, 'status': 'infrastructure_error', 'detail': str(error), 'image_id': image_id}
    finally:
        docker('rm', '--force', name, check=False)


def summarize(rows, task_count):
    paired = [r for r in rows if r.get('environment_valid')]
    valid_ids = {r['instance_id'] for r in paired if r['variant'] == 'base'} & {r['instance_id'] for r in paired if r['variant'] == 'adapter'}
    variants = {}
    for variant in ['base', 'adapter']:
        eligible = [r for r in paired if r['variant'] == variant and r['instance_id'] in valid_ids]
        variants[variant] = {'paired_eligible_tasks': len(eligible),
            'strict_upstream_f2p_reproduced_tasks': sum(r.get('strict_upstream_f2p_reproduced', False) for r in eligible),
            'passed': sum(r.get('candidate_passed', False) for r in eligible),
            'pass_rate': sum(r.get('candidate_passed', False) for r in eligible)/len(eligible) if eligible else None,
            'format_valid': sum(r.get('format_valid', False) for r in eligible),
            'patch_applies': sum(r.get('patch_applies', False) for r in eligible),
            'tasks_with_regressions': sum(r.get('pass_to_pass_preserved', 0) < r.get('pass_to_pass_total', 0) for r in eligible),
            'status_counts_all_attempts': dict(Counter(r['status'] for r in rows if r['variant'] == variant))}
    return {'scope': 'development_only_not_terminal_bench', 'protocol_version': 'repair-dev20-execution-v2', 'frozen_tasks_requested': task_count,
            'paired_environment_valid_tasks': len(valid_ids), 'variants': variants,
            'note': 'Missing/invalid environments are reported separately, never counted as successful repairs. No resampling.'}


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', type=Path, default=root/'data/evaluation/repair-dev20-v1')
    parser.add_argument('--predictions', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--limit', type=int, default=20, help='Use 1 for execution preflight, 20 for the frozen comparison')
    parser.add_argument('--pull-missing', action='store_true', help='Explicitly allow large official Docker image downloads')
    args = parser.parse_args()
    manifest, tasks, records = validate_predictions(args.packet, args.predictions)
    if args.limit not in [1, 20]:
        parser.error('Use --limit 1 or --limit 20; the task order is frozen')
    docker('info', '--format', '{{.ServerVersion}}')
    out = args.output or root/'results/repair_eval'/('repair-dev20-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(parents=True, exist_ok=False)
    (out/'generation_results.json').write_bytes(args.predictions.read_bytes())
    (out/'packet_manifest.json').write_bytes((args.packet/'public/manifest.json').read_bytes())
    (out/'run_provenance.json').write_text(json.dumps({'predictions_sha256': sha(args.predictions.read_bytes()), 'packet_manifest_sha256': sha((args.packet/'public/manifest.json').read_bytes()), 'limits': {'cpus': 2, 'memory': '4g', 'network': 'none'}, 'tasks_requested': args.limit, 'protocol_version': 'repair-dev20-execution-v2', 'evaluator_sources_sha256': {name: sha((root/'training'/name).read_bytes()) for name in ['repair_eval_common.py', 'repair_eval_container.py', 'run_repair_eval.py']}}, indent=2), encoding='utf-8')
    selected = tasks[:args.limit]; reports = []
    for index, task in enumerate(selected, 1):
        for variant in manifest['variants']:
            row = run_one(root, task, records[(task['instance_id'], variant)],
                          out/(sha(task['instance_id'])[:16] + '-' + variant), args.pull_missing)
            reports.append(row)
            (out/'reports.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')
            (out/'summary.json').write_text(json.dumps(summarize(reports, len(selected)), indent=2), encoding='utf-8')
            print(index, '/', len(selected), variant, task['instance_id'], row['status'], flush=True)
    print('Saved comparison:', out/'summary.json')


if __name__ == '__main__':
    main()
