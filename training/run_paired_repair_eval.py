"""Run paired unified-diff repairs with the established frozen reference controls."""
import json
from pathlib import Path
import sys
import time
import uuid


def execute_paired(root,task,candidate,out,snapshot):
    from run_repair_eval import docker
    report_base={'instance_id':task['instance_id'],'variant':candidate['variant'],'environment_valid':False,'candidate_passed':False}
    inspected=docker('image','inspect',task['image_name'],check=False)
    if inspected.returncode:return {**report_base,'status':'image_unavailable'}
    image=json.loads(inspected.stdout)[0]
    name='svaga-paired-'+uuid.uuid4().hex[:16]
    out.mkdir(parents=True,exist_ok=False)
    # A protocol flag enables only established header-derived p0/p1 compatibility; task source/test data remain unchanged.
    payload=out/'execution-input.json'
    payload.write_text(json.dumps({'task':{**task,'_path_compatibility':True},'candidate':candidate}),encoding='utf-8')
    started=time.perf_counter()
    try:
        docker('run','--detach','--name',name,'--network','none','--cpus','2','--memory','4g',
            '--pids-limit','256','--cap-drop','ALL','--security-opt','no-new-privileges',
            '--entrypoint','/bin/sh',image['Id'],'-c','sleep infinity')
        interpreter=docker('exec',name,'/bin/sh','-c',
            'for p in /opt/miniconda3/envs/testbed/bin/python /testbed/.venv/bin/python /opt/venv/bin/python; do if [ -x "$p" ]; then echo "$p"; exit 0; fi; done; command -v python').stdout.strip()
        if not interpreter.startswith('/') or '\n' in interpreter:raise ValueError('Invalid image Python interpreter')
        for source in snapshot.glob('*.py'):docker('cp',str(source),name+':/tmp/'+source.name)
        docker('cp',str(payload),name+':/tmp/svaga-eval-task.json')
        try:
            result=docker('exec',name,interpreter,'/tmp/run_paired_repair_eval.py','--inside',timeout=2600,check=False)
            (out/'container.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
        finally:docker('cp',name+':/tmp/svaga-generated-evaluation',str(out/'evidence'),check=False)
        report=json.loads((out/'evidence/report.json').read_text(encoding='utf-8'))
        assert (report['instance_id'],report['variant'])==(task['instance_id'],candidate['variant'])
        report.update(image_id=image['Id'],image_ref=task['image_name'],image_repo_digests=image.get('RepoDigests',[]),execution_seconds=time.perf_counter()-started)
        return report
    except Exception as exc:return {**report_base,'status':'infrastructure_error','detail':type(exc).__name__+': '+str(exc),'image_id':image['Id']}
    finally:docker('rm','--force',name,check=False)


def host_main():
    import argparse
    from repair_eval_common import sha
    from run_repair_eval import validate_predictions,docker,summarize
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet',type=Path,required=True)
    parser.add_argument('--predictions',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--limit',type=int,choices=[1,20],default=20)
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    manifest,tasks,records=validate_predictions(args.packet,args.predictions)
    assert manifest['variants']==['base','adapter'] and manifest['tasks']==20
    data=json.loads(args.predictions.read_text(encoding='utf-8'))
    original_base=root/'results/repair_eval_inputs/repair-dev20-qwen3coder30b-base-v1/qwen3coder30b_dev20_base_generations.json'
    assert sha(original_base.read_bytes())==manifest['base_generation_sha256']==data['base_generation_sha256']
    assert [r for r in data['records'] if r['variant']=='base']==json.loads(original_base.read_text(encoding='utf-8'))['records']
    docker('info','--format','{{.ServerVersion}}')
    selected=tasks[:args.limit]
    missing=[image for image in sorted({t['image_name'] for t in selected}) if docker('image','inspect',image,check=False).returncode]
    if missing:raise RuntimeError('Official images missing; no images downloaded automatically: '+repr(missing))
    names=['repair_eval_common.py','repair_eval_container.py','repair_eval_image_metadata.py','retry_repair_eval_metadata.py','run_paired_repair_eval.py']
    provenance={'protocol':'frozen-v2-reference-controls-plus-existing-native-path-and-packaging-compatibility',
        'scope':'same frozen development tasks; not Terminal-Bench or application-security certification',
        'model':manifest['model'],'revision':manifest['model_revision'],'predictions_sha256':sha(args.predictions.read_bytes()),
        'packet_manifest_sha256':sha((args.packet/'public/manifest.json').read_bytes()),
        'tasks_requested':args.limit,'limits':{'network':'none','cpus':2,'memory':'4g','pids':256,'host_mounts':False},
        'raw_generated_diff_rewritten':False,'fuzzy_matching':False,
        'evaluator_sources_sha256':{name:sha((root/'training'/name).read_bytes()) for name in names}}
    out=args.output
    if args.resume:
        assert json.loads((out/'provenance.json').read_text(encoding='utf-8'))==provenance,'Resume inputs/sources changed'
        reports=json.loads((out/'reports.json').read_text(encoding='utf-8'))
    else:
        out.mkdir(parents=True,exist_ok=False);snapshot=out/'evaluator-sources';snapshot.mkdir()
        for name in names:(snapshot/name).write_bytes((root/'training'/name).read_bytes())
        (out/'provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
        (out/'generation_results.json').write_bytes(args.predictions.read_bytes())
        (out/'packet_manifest.json').write_bytes((args.packet/'public/manifest.json').read_bytes())
        reports=[];(out/'reports.json').write_text('[]',encoding='utf-8')
    snapshot=out/'evaluator-sources'
    for name,digest in provenance['evaluator_sources_sha256'].items():assert sha((snapshot/name).read_bytes())==digest
    allowed={(t['instance_id'],v) for t in selected for v in manifest['variants']}
    completed={(r['instance_id'],r['variant']) for r in reports}
    assert len(completed)==len(reports) and completed<=allowed
    for index,task in enumerate(selected,1):
        for variant in manifest['variants']:
            key=(task['instance_id'],variant)
            if key in completed:continue
            attempt=out/(sha(task['instance_id'])[:16]+'-'+variant+'-'+uuid.uuid4().hex[:6])
            report=execute_paired(root,task,records[key],attempt,snapshot)
            report['attempt_directory']=attempt.name;reports.append(report);completed.add(key)
            temporary=out/'reports.tmp';temporary.write_text(json.dumps(reports,indent=2),encoding='utf-8');temporary.replace(out/'reports.json')
            summary=summarize(reports,len(selected))
            summary.update(protocol_version=provenance['protocol'],completed_variant_records=len(reports),
                comparison_complete=completed==allowed,model=manifest['model'],revision=manifest['model_revision'])
            (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
            print(index,'/',len(selected),variant,task['instance_id'],report['status'],flush=True)
    print('Saved:',out/'summary.json',flush=True)


if __name__=='__main__':
    if sys.argv[1:]==['--inside']:
        from retry_repair_eval_metadata import container_main
        container_main()
    else:host_main()
