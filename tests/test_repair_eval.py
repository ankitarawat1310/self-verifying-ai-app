import xml.etree.ElementTree as ET
import pytest
from training.repair_eval_common import select_tasks, extract_diff, patch_paths, selector_key, junit_outcomes, all_passed

DIFF = '--- a/src/app.py\n+++ b/src/app.py\n@@ -1 +1 @@\n-return 0\n+return 1\n'


def test_selection_is_order_independent_and_repository_balanced():
    rows = [{'instance_id': f'{repo}-{i}', 'repo': repo} for repo in ['one', 'two', 'three'] for i in range(10)]
    first = select_tasks(rows, 8)
    assert [r['instance_id'] for r in first] == [r['instance_id'] for r in select_tasks(list(reversed(rows)), 8)]
    assert len({r['instance_id'] for r in first}) == 8
    counts = [sum(r['repo'] == repo for r in first) for repo in ['one', 'two', 'three']]
    assert max(counts) - min(counts) <= 1


def test_diff_parser_accepts_only_the_same_allowed_source_patch():
    assert extract_diff('```diff\n' + DIFF + '```', ['src/app.py']) == DIFF
    assert patch_paths(DIFF) == {'src/app.py'}


@pytest.mark.parametrize('text', [DIFF.replace('src/app.py', '../escape.py'),
    DIFF.replace('src/app.py', 'tests/test_app.py'), 'Here is a fix:\n' + DIFF,
    DIFF.replace('+++ b/src/app.py', '+++ /dev/null'), DIFF + 'new file mode 100644\n'])
def test_diff_rejects_path_escape_test_edits_prose_and_file_operations(text):
    with pytest.raises(ValueError):
        extract_diff(text, ['src/app.py'])


def test_exit_zero_without_all_named_tests_is_not_success():
    expected = {'tests.test_app::test_one', 'tests.test_app::test_two'}
    assert not all_passed({'exit_code': 0, 'outcomes': {'tests.test_app::test_one': 'passed'}}, expected)
    assert not all_passed({'exit_code': 0, 'outcomes': {k: 'skipped' for k in expected}}, expected)
    assert all_passed({'exit_code': 0, 'outcomes': {k: 'passed' for k in expected}}, expected)


def test_junit_identity_preserves_class_and_parameter_and_detects_duplicates(tmp_path):
    assert selector_key('tests/test_app.py::TestAPI::test_one[blue]') == 'tests.test_app.TestAPI::test_one[blue]'
    path = tmp_path/'result.xml'
    path.write_text('<testsuite><testcase classname="tests.test_app.TestAPI" name="test_one[blue]"/></testsuite>')
    assert junit_outcomes(path) == {'tests.test_app.TestAPI::test_one[blue]': 'passed'}
    path.write_text('<testsuite><testcase classname="x" name="a"/><testcase classname="x" name="a"/></testsuite>')
    with pytest.raises(ValueError):
        junit_outcomes(path)


@pytest.mark.parametrize('selector', ['--ignore=x', '../test_app.py::test_x', '/tmp/test_app.py::test_x'])
def test_selectors_cannot_be_options_or_outside_paths(selector):
    with pytest.raises(ValueError):
        selector_key(selector)


def test_reviewed_mido_path_mapping_is_explicit_and_repo_limited():
    from training.repair_eval_common import normalize_official_selector
    assert normalize_official_selector('../dev/tests/test_x.py::test_a', 'swesmith/mido__mido.abc') == 'tests/test_x.py::test_a'
    with pytest.raises(ValueError):
        normalize_official_selector('../dev/tests/test_x.py::test_a', 'some/other')
    assert selector_key('tests/test_x.py::test_a[foo::bar]') == 'tests.test_x::test_a[foo::bar]'



def test_summary_reports_only_paired_valid_environments_and_keeps_failures():
    from training.run_repair_eval import summarize
    rows = [
        {'instance_id': 'a', 'variant': 'base', 'environment_valid': True, 'candidate_passed': False, 'status': 'tests_failed'},
        {'instance_id': 'a', 'variant': 'adapter', 'environment_valid': True, 'candidate_passed': True, 'status': 'passed'},
        {'instance_id': 'b', 'variant': 'base', 'environment_valid': False, 'candidate_passed': False, 'status': 'image_unavailable'},
        {'instance_id': 'b', 'variant': 'adapter', 'environment_valid': True, 'candidate_passed': True, 'status': 'passed'},
    ]
    result = summarize(rows, 2)
    assert result['paired_environment_valid_tasks'] == 1
    assert result['variants']['base']['passed'] == 0
    assert result['variants']['adapter']['passed'] == 1
    assert result['variants']['base']['status_counts_all_attempts']['image_unavailable'] == 1


@pytest.mark.parametrize('fix_correctly', [True, False])
def test_authored_synthetic_reference_and_generated_patch_flow(tmp_path, monkeypatch, fix_correctly):
    # Authored toy code only: no downloaded/model output is executed on the host.
    import subprocess
    from training import repair_eval_container as runner
    from training.repair_eval_common import sha
    repository = tmp_path/'repository'; repository.mkdir()
    evidence = tmp_path/'evidence'; evidence.mkdir()
    (repository/'tests').mkdir()
    (repository/'app.py').write_text('def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n'.replace('\\n', '\n'))
    (repository/'tests/test_app.py').write_text('from app import add, multiply\n\ndef test_add():\n    assert add(2, 3) == 5\n\ndef test_multiply():\n    assert multiply(2, 3) == 6\n'.replace('\\n', '\n'))
    def git(*args):
        return subprocess.run(['git', '-C', str(repository), *args], check=True, capture_output=True, text=True).stdout
    git('init', '-q')
    git('config', 'core.autocrlf', 'false'); git('config', 'core.eol', 'lf')
    for path in [repository/'app.py', repository/'tests/test_app.py']:
        path.write_bytes(path.read_text().encode('utf-8'))
    git('add', 'app.py', 'tests/test_app.py')
    git('-c', 'user.name=SVAGA Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'authored clean fixture')
    code = (repository/'app.py').read_text()
    (repository/'app.py').write_bytes(code.replace('return a + b', 'return a - b').encode('utf-8'))
    bug = git('diff', '--', 'app.py')
    git('checkout', '--', 'app.py')
    task = {'instance_id': 'authored-test', 'repo': 'authored/test', 'source_revision': 'test', 'patch': bug,
            'allowed_paths': ['app.py'], 'FAIL_TO_PASS': ['tests/test_app.py::test_add'],
            'PASS_TO_PASS': ['tests/test_app.py::test_multiply'], 'test_timeout_seconds': 30}
    answer = 'return a + b' if fix_correctly else 'return a * b'
    import difflib
    buggy_source = code.replace('return a + b', 'return a - b')
    repaired_source = buggy_source.replace('return a - b', answer)
    diff = ''.join(difflib.unified_diff(buggy_source.splitlines(keepends=True), repaired_source.splitlines(keepends=True), fromfile='a/app.py', tofile='b/app.py'))
    candidate = {'variant': 'adapter', 'text': diff, 'hit_token_limit': False}
    monkeypatch.setattr(runner, 'ROOT', repository)
    monkeypatch.setattr(runner, 'OUT', evidence)
    monkeypatch.setenv('PYTEST_DISABLE_PLUGIN_AUTOLOAD', '1')
    result = runner.evaluate(task, candidate)
    assert result['environment_valid'] is True
    assert result['candidate_passed'] is fix_correctly, result
    assert result['status'] == ('passed' if fix_correctly else 'tests_failed')
    assert result['pass_to_pass_preserved'] == result['pass_to_pass_total'] == 1



def test_diff_preserves_required_trailing_blank_context_lines():
    text = DIFF.replace('@@ -1 +1 @@', '@@ -1,2 +1,2 @@') + ' \n'
    assert extract_diff(text, ['src/app.py']) == text
    assert extract_diff('```diff\n' + text + '```\n', ['src/app.py']) == text



def test_prediction_packet_integrity_and_complete_pair_requirement(tmp_path):
    import json
    from training.repair_eval_common import sha
    from training.run_repair_eval import validate_predictions
    packet = tmp_path/'packet'; (packet/'public').mkdir(parents=True)
    tasks = [{'instance_id': 'a', 'prompt_sha256': 'prompt-a'}]
    private_raw = (json.dumps(tasks[0]) + '\n').encode()
    public_raw = (json.dumps({'instance_id': 'a', 'prompt_sha256': 'prompt-a'}) + '\n').encode()
    (packet/'private_tasks.jsonl').write_bytes(private_raw)
    (packet/'public/prompts.jsonl').write_bytes(public_raw)
    manifest = {'model': 'fixture', 'model_revision': 'pin', 'tasks': 1, 'variants': ['base', 'adapter'],
                'decoding': {}, 'adapter_artifacts_sha256': {}, 'private_tasks_sha256': sha(private_raw),
                'prompts_sha256': sha(public_raw)}
    raw = json.dumps(manifest).encode(); (packet/'public/manifest.json').write_bytes(raw)
    data = {'manifest_sha256': sha(raw), 'model': 'fixture', 'revision': 'pin', 'decoding': {},
            'adapter_artifacts_sha256': {}, 'records': [
                {'instance_id': 'a', 'variant': variant, 'prompt_sha256': 'prompt-a', 'text': DIFF, 'hit_token_limit': False}
                for variant in ['base', 'adapter']]}
    predictions = tmp_path/'predictions.json'; predictions.write_text(json.dumps(data))
    assert len(validate_predictions(packet, predictions)[2]) == 2
    data['records'].pop(); predictions.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='completed generations'):
        validate_predictions(packet, predictions)
    (packet/'private_tasks.jsonl').write_bytes(private_raw + b' ')
    with pytest.raises(AssertionError):
        validate_predictions(packet, predictions)



def test_conflicting_git_header_cannot_hide_an_unauthorized_file():
    with pytest.raises(ValueError):
        extract_diff('diff --git a/tests/test_app.py b/tests/test_app.py\n' + DIFF, ['src/app.py'])



@pytest.mark.parametrize('separator', ['\t', '   '])
def test_git_compatible_backup_and_timestamp_headers_preserve_original_output(separator):
    text = DIFF.replace('--- a/src/app.py', '--- a/src/app.py.orig' + separator + '2023-01-01 00:00:00 +0000')
    text = text.replace('+++ b/src/app.py', '+++ b/src/app.py' + separator + '2023-01-01 00:00:00 +0000')
    assert extract_diff(text, ['src/app.py']) == text
    with pytest.raises(ValueError):
        extract_diff(text.replace('app.py.orig', 'other.py.orig'), ['src/app.py'])


def test_observed_failures_do_not_credit_already_passing_upstream_tests():
    from training.repair_eval_common import observed_bug_failures
    stage = {'exit_code': 1, 'outcomes': {'a': 'failed', 'b': 'passed', 'c': 'passed'}}
    assert observed_bug_failures(stage, ['a', 'b'], ['c']) == ['a']
    stage['outcomes']['c'] = 'failed'
    with pytest.raises(ValueError):
        observed_bug_failures(stage, ['a', 'b'], ['c'])
    with pytest.raises(ValueError):
        observed_bug_failures({'exit_code': 0, 'outcomes': {'a': 'passed'}}, ['a'], [])



def test_image_download_failure_is_reported_without_stopping_the_grid(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from training import run_repair_eval as runner
    def fake_docker(*args, **kwargs):
        if args[0] == 'image':
            return SimpleNamespace(returncode=1)
        if args[0] == 'pull':
            raise RuntimeError('authored registry failure')
        raise AssertionError('Unexpected Docker action')
    monkeypatch.setattr(runner, 'docker', fake_docker)
    result = runner.run_one(tmp_path, {'instance_id': 'fixture', 'image_name': 'fixture/image'},
                            {'variant': 'base'}, tmp_path/'output', True)
    assert result['status'] == 'image_download_error' and not result['candidate_passed']
    assert result['environment_valid'] is False
