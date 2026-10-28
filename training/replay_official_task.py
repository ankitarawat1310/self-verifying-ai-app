"""Run inside the isolated official task container, not on the host.

Apply the official bug patch to its clean base, then reverse it. Execute the
listed tests at all three states and preserve JUnit evidence and source hashes.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import re
import os
import xml.etree.ElementTree as ET


def run(args, **kwargs):
    return subprocess.run(args, cwd='/testbed', text=True, capture_output=True, timeout=600, **kwargs)


def checked(args):
    result=run(args)
    if result.returncode:raise RuntimeError(f'{args}: {result.stdout}\n{result.stderr}')
    return result.stdout.strip()


def main():
    task=json.loads(Path('/tmp/svaga-task.json').read_text())
    out=Path('/tmp/svaga-replay');out.mkdir(exist_ok=False)
    assert Path('/testbed/.git').exists()
    # Container filesystem is disposable; never mount the user's checkout here.
    assert not checked(['git','status','--porcelain']), 'Image repository is dirty'
    base=checked(['git','rev-parse','HEAD'])
    # Official image uses a flattened initial commit, not upstream Git history.
    # Verify every touched file against the patch's pre-bug Git blob instead.
    verified_blobs={}
    for section in task['patch'].split('diff --git ')[1:]:
        header=re.match(r'a/(\S+) b/(\S+)\nindex ([0-9a-f]+)\.\.([0-9a-f]+)',section)
        assert header and header[1]==header[2], 'Unsupported patch header'
        path=header[1]
        assert not path.startswith('/') and '..' not in path.split('/')
        actual=checked(['git','hash-object',path])
        assert actual.startswith(header[3]), f'Pre-bug source mismatch: {path}'
        verified_blobs[path]=actual
    patch=out/'bug.patch';patch.write_text(task['patch'],encoding='utf-8')
    selectors=task['FAIL_TO_PASS']+task['PASS_TO_PASS']
    assert selectors and len(set(selectors))==len(selectors)
    stages=[]
    def test(stage):
        xml=out/f'{stage}.xml'
        # A fast same-size source edit can otherwise reuse timestamp-valid .pyc.
        env=dict(os.environ, PYTHONPYCACHEPREFIX=str(out/f'bytecode-{stage}'),
                 PATH=str(Path(sys.executable).parent)+os.pathsep+os.environ.get('PATH',''))
        result=run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',f'--junitxml={xml}',*selectors],env=env)
        (out/f'{stage}.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
        outcomes={}
        if xml.exists():
            for case in ET.parse(xml).iter('testcase'):
                name=case.attrib.get('name','');classname=case.attrib.get('classname','')
                key=classname+'::'+name
                state='failed' if case.find('failure') is not None else 'error' if case.find('error') is not None else 'skipped' if case.find('skipped') is not None else 'passed'
                outcomes[key]=state
        record={'stage':stage,'exit_code':result.returncode,'outcomes':outcomes}
        stages.append(record)
        print(stage,'exit',result.returncode,'outcomes',dict(__import__('collections').Counter(outcomes.values())),flush=True)
    test('clean_baseline')
    assert stages[-1]['exit_code']==0,'Clean baseline tests failed; stop before patching'
    checked(['git','apply','--check',str(patch)])
    checked(['git','apply',str(patch)])
    (out/'buggy.diff').write_text(checked(['git','diff']),encoding='utf-8')
    test('buggy')
    checked(['git','apply','--reverse','--check',str(patch)])
    checked(['git','apply','--reverse',str(patch)])
    assert not checked(['git','diff','--name-only']), 'Reverse patch did not restore tracked code'
    test('repaired')
    report={'instance_id':task['instance_id'],'base_commit':base,'python':sys.version,
            'verified_pre_bug_blobs':verified_blobs,'base_history':'official image flattened initial commit',
            'patch_sha256':hashlib.sha256(task['patch'].encode()).hexdigest(),'test_selectors':selectors,
            'stages':stages,'method':'clean base -> official bug patch -> reverse same patch',
            'scope':'training-data replay sanity check; no model-generated repair evaluated'}
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    assert stages[1]['exit_code']==1 and any(v=='failed' for v in stages[1]['outcomes'].values()),'Expected a genuine buggy test failure'
    assert stages[2]['exit_code']==0,'Repair did not pass tests'
    print('Replay sequence completed; inspect named failure against task metadata.')


if __name__=='__main__':main()
