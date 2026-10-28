"""Launch one selected official task in a disposable, network-free container."""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name',choices=['iniconfig','funcy','typeguard','schema'])
    parser.add_argument('--attempt',type=int,default=1)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    out=root/f'data/audits/{args.name}-replay-20261025'
    task_path=out/'task.json'
    task=json.loads(task_path.read_text())
    container=f'svaga-{args.name}-replay-20261025'
    if args.attempt!=1:
        assert args.attempt>1
        out=out/f'attempt-{args.attempt}'
        out.mkdir(exist_ok=False)
        container+=f'-attempt{args.attempt}'
    def docker(*words,check=True):
        r=subprocess.run(['docker',*words],capture_output=True,text=True,timeout=600)
        if check and r.returncode:raise RuntimeError(r.stdout+'\n'+r.stderr)
        return r
    image=json.loads(docker('image','inspect',task['image_name']).stdout)[0]
    digest=image['RepoDigests'][0]
    docker('run','--detach','--name',container,'--network','none','--cpus','2','--memory','4g',
           '--pids-limit','256','--cap-drop','ALL','--security-opt','no-new-privileges',
           '--entrypoint','/bin/bash',digest,'-c','sleep infinity')
    try:
        env=docker('exec',container,'/bin/bash','-lc',
                   'for p in /opt/miniconda3/envs/testbed/bin/python /testbed/.venv/bin/python /opt/venv/bin/python; do if [ -x "$p" ]; then echo "$p"; exit 0; fi; done; command -v python').stdout.strip()
        assert env.startswith('/'),env
        docker('cp',str(root/'training/replay_official_task.py'),container+':/tmp/replay_official_task.py')
        docker('cp',str(task_path),container+':/tmp/svaga-task.json')
        result=docker('exec',container,env,'/tmp/replay_official_task.py',check=False)
        (out/'runner.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
        docker('cp',container+':/tmp/svaga-replay',str(out/'evidence'),check=False)
        metadata={'container':container,'image_digest':digest,'interpreter':env,'runner_exit_code':result.returncode}
        (out/'execution.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        print(result.stdout,result.stderr,flush=True)
        if result.returncode:raise RuntimeError('Replay failed; inspect runner.log')
    finally:
        docker('stop',container,check=False)


if __name__=='__main__':main()
