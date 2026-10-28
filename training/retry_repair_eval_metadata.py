"""Supplement only image-metadata failures; preserve the frozen v2 evaluator/results."""
import json
from pathlib import Path
import sys
import uuid


def container_main():
    import repair_eval_container as frozen
    from repair_eval_image_metadata import validate_packaging_status, derived_strip_level
    original = frozen.checked
    metadata = []
    chosen_strip_levels = []
    payload = json.loads(Path('/tmp/svaga-eval-task.json').read_text(encoding='utf-8'))
    use_paths = payload['task'].get('_path_compatibility', False)
    if use_paths:
        original_run = frozen.run
        def path_run(args, **kwargs):
            if args[:2] == ['git', 'apply'] and args[-1] == str(frozen.OUT/'generated.patch'):
                level = derived_strip_level((frozen.OUT/'generated.patch').read_text(encoding='utf-8'))
                chosen_strip_levels.append(level)
                args = [*args[:2], '-p' + str(level), *args[2:]]
            return original_run(args, **kwargs)
        frozen.run = path_run
    def metadata_checked(args):
        result = original(args)
        if args == ['git', 'status', '--porcelain']:
            metadata.extend(validate_packaging_status(result, frozen.ROOT))
            return ''  # All tracked modifications and other untracked content still raise.
        return result
    frozen.checked = metadata_checked
    frozen.main()
    path = frozen.OUT/'report.json'
    report = json.loads(path.read_text(encoding='utf-8'))
    report['protocol_version'] = 'repair-dev20-native-path-and-packaging-compatibility' if use_paths else 'repair-dev20-v2-packaging-metadata-compatibility'
    report['generated_patch_strip_level'] = chosen_strip_levels[0] if chosen_strip_levels else None
    report['raw_generated_diff_rewritten'] = False
    report['initial_packaging_metadata_preserved'] = metadata
    report['compatibility_scope'] = 'Ignore only validated preinstalled text .egg-info metadata in the initial cleanliness check; original source/blob/test/patch controls unchanged.'
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')


def host_main():
    import argparse
    from run_repair_eval import docker, summarize
    from resume_repair_eval import load_resume
    from repair_eval_common import sha, extract_diff
    from repair_eval_image_metadata import derived_strip_level
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', type=Path, default=root/'results/repair_eval/repair-dev20-full-v2-20261025')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--path-compatibility', action='store_true')
    parser.add_argument('--previous-combined', type=Path, default=root/'results/repair_eval/repair-dev20-metadata-compat-20261026/combined_reports.json')
    args = parser.parse_args()
    packet = root/'data/evaluation/repair-dev20-v1'
    predictions = root/'results/repair_eval_inputs/repair-dev20-v1/generation_results.json'
    manifest,tasks,records,original,completed = load_resume(root,packet,predictions,args.original)
    if len(completed) != 40:
        raise ValueError('Finish and preserve the original 40-result run first')
    unresolved_paths = []
    if args.path_compatibility:
        prior = json.loads(args.previous_combined.read_text(encoding='utf-8'))
        assert {(r['instance_id'],r['variant']) for r in prior} == completed and len(prior)==40
        prior_provenance = json.loads((args.previous_combined.parent/'provenance.json').read_text(encoding='utf-8'))
        assert prior_provenance['generation_sha256'] == sha(predictions.read_bytes())
        original = prior
        task_lookup = {t['instance_id']:t for t in tasks}
        retry_rows = []
        for row in original:
            key = (row['instance_id'],row['variant'])
            if records[key]['hit_token_limit']:
                continue  # Remains a generation-limit failure, regardless of header style.
            diff = extract_diff(records[key]['text'],task_lookup[key[0]]['allowed_paths'])
            try:
                level = derived_strip_level(diff)
            except ValueError as error:
                unresolved_paths.append({'instance_id':key[0],'variant':key[1],'reason':str(error)})
                continue  # No guessing/trying multiple strip levels; preserve the previous failure.
            if level==0:
                retry_rows.append(row)
    else:
        retry_rows = [row for row in original if row['status']=='execution_error'
                      and row.get('detail')=='ValueError: Official image starts dirty']
    docker('info','--format','{{.ServerVersion}}')
    out = args.output or root/('results/repair_eval/repair-dev20-native-path-compat-20261026' if args.path_compatibility else 'results/repair_eval/repair-dev20-metadata-compat-20261026'); out.mkdir(parents=True,exist_ok=False)
    names = ['repair_eval_common.py','repair_eval_container.py','repair_eval_image_metadata.py','retry_repair_eval_metadata.py']
    snapshot = out/'evaluator-sources';snapshot.mkdir()
    for name in names:(snapshot/name).write_bytes((root/'training'/name).read_bytes())
    info={'base_protocol':'repair-dev20-execution-v2','compatibility':'validated text .egg-info and deterministic native Git strip-level handling' if args.path_compatibility else 'initial untracked text .egg-info only',
          'evaluator_sources_sha256':{name:sha((snapshot/name).read_bytes()) for name in names},
          'generation_sha256':sha(predictions.read_bytes()),'original_directory':str(args.original)}
    info['unresolved_path_styles_kept_as_original_failures'] = unresolved_paths
    info['previous_combined'] = str(args.previous_combined) if args.path_compatibility else None
    info['retry_selection'] = [{'instance_id':r['instance_id'],'variant':r['variant']} for r in retry_rows]
    (out/'provenance.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
    lookup={task['instance_id']:task for task in tasks};supplement=[]
    for old in retry_rows:
        task=lookup[old['instance_id']];variant=old['variant'];candidate=records[(task['instance_id'],variant)]
        image=json.loads(docker('image','inspect',old['image_ref']).stdout)[0]
        if image['Id'] != old['image_id']:raise ValueError('Official image changed')
        attempt=out/(sha(task['instance_id'])[:16]+'-'+variant);attempt.mkdir()
        payload=attempt/'execution-input.json';payload.write_text(json.dumps({'task':{**task,'_path_compatibility':args.path_compatibility},'candidate':candidate}),encoding='utf-8')
        container='svaga-metadata-retry-'+uuid.uuid4().hex[:12]
        try:
            docker('run','--detach','--name',container,'--network','none','--cpus','2','--memory','4g',
                   '--pids-limit','256','--cap-drop','ALL','--security-opt','no-new-privileges',
                   '--entrypoint','/bin/sh',image['Id'],'-c','sleep infinity')
            python=docker('exec',container,'/bin/sh','-c',
                'for p in /opt/miniconda3/envs/testbed/bin/python /testbed/.venv/bin/python /opt/venv/bin/python; do if [ -x "$p" ]; then echo "$p"; exit 0; fi; done; command -v python').stdout.strip()
            if not python.startswith('/') or '\n' in python:raise ValueError('Invalid image interpreter')
            for name in names:docker('cp',str(snapshot/name),container+':/tmp/'+name)
            docker('cp',str(payload),container+':/tmp/svaga-eval-task.json')
            try:
                run=docker('exec',container,python,'/tmp/retry_repair_eval_metadata.py','--inside',timeout=2600,check=False)
                (attempt/'container.log').write_text(run.stdout+'\n'+run.stderr,encoding='utf-8')
            finally:docker('cp',container+':/tmp/svaga-generated-evaluation',str(attempt/'evidence'),check=False)
            report=json.loads((attempt/'evidence/report.json').read_text(encoding='utf-8'))
            if report['instance_id']!=task['instance_id'] or report['variant']!=variant:raise ValueError('Wrong report identity')
            report.update(image_id=image['Id'],image_ref=old['image_ref'],image_repo_digests=image.get('RepoDigests',[]))
        except Exception as error:
            report={'instance_id':task['instance_id'],'variant':variant,'status':'infrastructure_error',
                    'environment_valid':False,'candidate_passed':False,'detail':str(error)}
        finally:docker('rm','--force',container,check=False)
        supplement.append(report)
        (out/'supplementary_reports.json').write_text(json.dumps(supplement,indent=2),encoding='utf-8')
        print(variant,task['instance_id'],report['status'],flush=True)
    replacements={(row['instance_id'],row['variant']):row for row in supplement}
    combined=[replacements.get((row['instance_id'],row['variant']),row) for row in original]
    summary=summarize(combined,20)
    summary.update(protocol_version='repair-dev20-native-path-and-packaging-compatibility' if args.path_compatibility else 'repair-dev20-v2-with-recorded-packaging-compatibility',
                   original_v2_directory=str(args.original),supplementary_metadata_attempts=len(supplement),
                   completed_variant_records=len(combined),
                   compatibility_note='Original reports preserved. Installed text packaging metadata retained and hashed; native Git -p0/-p1 derived only from diff headers. Original outputs, source/blob checks and all test controls unchanged; no task replacement or patch rewriting.')
    (out/'combined_reports.json').write_text(json.dumps(combined,indent=2),encoding='utf-8')
    (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print('Saved supplementary and combined evidence:',out,flush=True)


if __name__=='__main__':
    if sys.argv[1:]==['--inside']:container_main()
    else:host_main()
