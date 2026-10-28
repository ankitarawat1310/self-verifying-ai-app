"""Execute exact edits with the frozen reference/test controls in fresh containers."""
import json
from pathlib import Path
import sys
import uuid


def install_edit_adapter(frozen):
    try:
        from .repair_eval_common import sha
        from .repair_eval_image_metadata import validate_packaging_status
        from .search_replace_edits import render_diff, EditError
    except ImportError:
        from repair_eval_common import sha
        from repair_eval_image_metadata import validate_packaging_status
        from search_replace_edits import render_diff, EditError
    original_checked=frozen.checked;metadata=[];application={}
    def checked(args):
        value=original_checked(args)
        if args==['git','status','--porcelain']:
            metadata.extend(validate_packaging_status(value,frozen.ROOT));return ''
        return value
    def exact_edits(text,allowed_paths):
        application['raw_output_sha256']=sha(text)
        try:
            diff,matches=render_diff(frozen.ROOT,text,allowed_paths)
            application['blocks']=matches
            application['tool_rendered_diff_sha256']=sha(diff)
            return diff
        except EditError as error:
            application['error_code']=error.code
            application['detail']=str(error)
            raise
    frozen.checked=checked;frozen.extract_diff=exact_edits
    return metadata,application


def annotate_report(report,metadata,application):
    if report['status']=='invalid_diff' and 'error_code' in application:
        report['status']=application['error_code']
    report.update(protocol_version='repair-dev20-exact-search-replace-v1',edit_format='exact_line_search_replace',
                  initial_packaging_metadata_preserved=metadata,edit_application=application,
                  fuzzy_matching=False,reference_answer_used_for_generated_edit=False)
    return report


def container_main():
    import repair_eval_container as frozen
    metadata,application=install_edit_adapter(frozen)
    frozen.main()
    path=frozen.OUT/'report.json'
    report=annotate_report(json.loads(path.read_text(encoding='utf-8')),metadata,application)
    path.write_text(json.dumps(report,indent=2),encoding='utf-8')


def execute(root,task,candidate,out,snapshot,pull_missing):
    from run_repair_eval import docker
    from repair_eval_common import sha
    import subprocess
    basic={'instance_id':task['instance_id'],'variant':candidate['variant'],
           'environment_valid':False,'candidate_passed':False,'edit_format':'exact_line_search_replace'}
    inspect=docker('image','inspect',task['image_name'],check=False)
    if inspect.returncode and pull_missing:
        try:
            print('Downloading official image:',task['image_name'],flush=True)
            docker('pull',task['image_name'],timeout=3600);inspect=docker('image','inspect',task['image_name'])
        except (RuntimeError,subprocess.TimeoutExpired) as error:
            return {**basic,'status':'image_download_error','detail':str(error)}
    if inspect.returncode:return {**basic,'status':'image_unavailable'}
    image=json.loads(inspect.stdout)[0];name='svaga-search-replace-'+uuid.uuid4().hex[:12]
    out.mkdir(parents=True,exist_ok=False)
    payload=out/'execution-input.json';payload.write_text(json.dumps({'task':task,'candidate':candidate}),encoding='utf-8')
    try:
        docker('run','--detach','--name',name,'--network','none','--cpus','2','--memory','4g',
               '--pids-limit','256','--cap-drop','ALL','--security-opt','no-new-privileges',
               '--entrypoint','/bin/sh',image['Id'],'-c','sleep infinity')
        python=docker('exec',name,'/bin/sh','-c',
          'for p in /opt/miniconda3/envs/testbed/bin/python /testbed/.venv/bin/python /opt/venv/bin/python; do if [ -x "$p" ]; then echo "$p"; exit 0; fi; done; command -v python').stdout.strip()
        if not python.startswith('/') or '\n' in python:raise ValueError('Invalid image interpreter')
        for file in snapshot.glob('*.py'):docker('cp',str(file),name+':/tmp/'+file.name)
        docker('cp',str(payload),name+':/tmp/svaga-eval-task.json')
        try:
            result=docker('exec',name,python,'/tmp/run_search_replace_eval.py','--inside',timeout=2600,check=False)
            (out/'container.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
        finally:docker('cp',name+':/tmp/svaga-generated-evaluation',str(out/'evidence'),check=False)
        report=json.loads((out/'evidence/report.json').read_text(encoding='utf-8'))
        if (report['instance_id'],report['variant']) != (task['instance_id'],candidate['variant']):raise ValueError('Wrong report identity')
        report.update(image_id=image['Id'],image_ref=task['image_name'],image_repo_digests=image.get('RepoDigests',[]))
        return report
    except Exception as error:return {**basic,'status':'infrastructure_error','detail':str(error)}
    finally:docker('rm','--force',name,check=False)


def host_main():
    import argparse
    from datetime import datetime,timezone
    from repair_eval_common import sha
    from run_repair_eval import validate_predictions,docker,summarize
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet',type=Path,default=root/'data/evaluation/repair-dev20-search-replace-v1')
    parser.add_argument('--predictions',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--limit',type=int,choices=[1,20],default=20)
    parser.add_argument('--pull-missing',action='store_true')
    args=parser.parse_args()
    manifest,tasks,records=validate_predictions(args.packet,args.predictions)
    if manifest.get('evaluation_id')!='repair-dev20-search-replace-v1' or manifest.get('edit_format')!='exact_line_search_replace':
        raise ValueError('Expected the separately frozen exact-edit experiment')
    docker('info','--format','{{.ServerVersion}}')
    out=args.output or root/'results/repair_eval'/('search-replace-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    if args.resume and args.output is None:parser.error('--resume needs the existing --output directory')
    names=['repair_eval_common.py','repair_eval_container.py','repair_eval_image_metadata.py','search_replace_edits.py','run_search_replace_eval.py']
    provenance={'protocol_version':'repair-dev20-exact-search-replace-v1','predictions_sha256':sha(args.predictions.read_bytes()),
        'packet_manifest_sha256':sha((args.packet/'public/manifest.json').read_bytes()),'tasks_requested':args.limit,
        'evaluator_sources_sha256':{name:sha((root/'training'/name).read_bytes()) for name in names}}
    if args.resume:
        if json.loads((out/'provenance.json').read_text(encoding='utf-8'))!=provenance:raise ValueError('Run inputs/evaluator changed')
        reports=json.loads((out/'reports.json').read_text(encoding='utf-8'))
    else:
        out.mkdir(parents=True,exist_ok=False);snapshot=out/'evaluator-sources';snapshot.mkdir()
        for name in names:(snapshot/name).write_bytes((root/'training'/name).read_bytes())
        (out/'provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
        (out/'generation_results.json').write_bytes(args.predictions.read_bytes())
        (out/'packet_manifest.json').write_bytes((args.packet/'public/manifest.json').read_bytes());reports=[]
        (out/'reports.json').write_text('[]',encoding='utf-8')
    snapshot=out/'evaluator-sources'
    for name,wanted in provenance['evaluator_sources_sha256'].items():
        if sha((snapshot/name).read_bytes())!=wanted:raise ValueError('Evaluator snapshot changed')
    selected=tasks[:args.limit];allowed={(t['instance_id'],v) for t in selected for v in manifest['variants']}
    completed={(r['instance_id'],r['variant']) for r in reports}
    if len(completed)!=len(reports) or not completed<=allowed:raise ValueError('Duplicate/unexpected saved results')
    for index,task in enumerate(selected,1):
        for variant in manifest['variants']:
            key=(task['instance_id'],variant)
            if key in completed:continue
            attempt=out/(sha(task['instance_id'])[:16]+'-'+variant+'-'+uuid.uuid4().hex[:6])
            row=execute(root,task,records[key],attempt,snapshot,args.pull_missing)
            row['attempt_directory']=attempt.name;reports.append(row);completed.add(key)
            temporary=out/'reports.tmp';temporary.write_text(json.dumps(reports,indent=2),encoding='utf-8');temporary.replace(out/'reports.json')
            summary=summarize(reports,len(selected));summary.update(protocol_version='repair-dev20-exact-search-replace-v1',
              edit_format='exact_line_search_replace',completed_variant_records=len(reports),comparison_complete=len(reports)==len(allowed),
              previous_format_baseline='repair-dev20-native-path-and-packaging-compatibility: base 0/20, adapter 0/20',
              experiment_note='Same weights and issue/source contexts; inference format/prompt ablation only. No training or fuzzy edit correction.')
            (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
            print(index,'/',len(selected),variant,task['instance_id'],row['status'],flush=True)
    print('Saved:',out/'summary.json')


if __name__=='__main__':
    if sys.argv[1:]==['--inside']:container_main()
    else:host_main()
