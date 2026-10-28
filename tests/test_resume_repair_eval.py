"""Resume must preserve completed evidence and reject changes to pinned inputs."""
import json
from pathlib import Path
import pytest
from training.repair_eval_common import sha
from training.resume_repair_eval import load_resume, atomic_json


def make_fixture(root):
    training=root/'training';training.mkdir()
    for name in ['repair_eval_common.py','repair_eval_container.py','run_repair_eval.py']:
        (training/name).write_bytes(b'authored fixture')
    packet=root/'packet';(packet/'public').mkdir(parents=True)
    task={'instance_id':'one','prompt_sha256':'prompt'}
    private=(json.dumps(task)+'\n').encode();public=(json.dumps(task)+'\n').encode()
    (packet/'private_tasks.jsonl').write_bytes(private)
    (packet/'public/prompts.jsonl').write_bytes(public)
    manifest={'model':'fixture','model_revision':'pin','tasks':1,'variants':['base','adapter'],
              'decoding':{},'adapter_artifacts_sha256':{},'private_tasks_sha256':sha(private),'prompts_sha256':sha(public)}
    manifest_raw=json.dumps(manifest).encode();(packet/'public/manifest.json').write_bytes(manifest_raw)
    generated={'manifest_sha256':sha(manifest_raw),'model':'fixture','revision':'pin','decoding':{},
               'adapter_artifacts_sha256':{},'records':[dict(task,variant=v,text='fixture',hit_token_limit=False) for v in ['base','adapter']]}
    predictions=root/'predictions.json';predictions.write_text(json.dumps(generated))
    run=root/'run';run.mkdir();(run/'generation_results.json').write_bytes(predictions.read_bytes())
    (run/'packet_manifest.json').write_bytes(manifest_raw)
    provenance={'protocol_version':'repair-dev20-execution-v2','tasks_requested':20,
                'evaluator_sources_sha256':{p.name:sha(p.read_bytes()) for p in training.iterdir()},
                'predictions_sha256':sha(predictions.read_bytes()),'packet_manifest_sha256':sha(manifest_raw)}
    (run/'run_provenance.json').write_text(json.dumps(provenance))
    (run/'reports.json').write_text(json.dumps([{'instance_id':'one','variant':'base','status':'passed'}]))
    return packet,predictions,run


def test_resume_keeps_completed_variant_and_requires_same_evaluator(tmp_path):
    packet,predictions,run=make_fixture(tmp_path)
    manifest,tasks,records,reports,completed=load_resume(tmp_path,packet,predictions,run)
    assert completed=={('one','base')} and ('one','adapter') not in completed
    (tmp_path/'training/repair_eval_common.py').write_bytes(b'changed')
    with pytest.raises(ValueError,match='Evaluator changed'):
        load_resume(tmp_path,packet,predictions,run)


def test_resume_rejects_duplicate_results_and_atomic_write_is_valid_json(tmp_path):
    packet,predictions,run=make_fixture(tmp_path)
    data=[{'instance_id':'one','variant':'base'}]*2
    atomic_json(run/'reports.json',data)
    assert json.loads((run/'reports.json').read_text())==data
    assert not (run/'reports.json.resume-tmp').exists()
    with pytest.raises(ValueError,match='Duplicate'):
        load_resume(tmp_path,packet,predictions,run)
