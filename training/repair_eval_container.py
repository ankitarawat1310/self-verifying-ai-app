"""Execute one generated patch inside a disposable official container only."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
try:
    from .repair_eval_common import sha, patch_paths, extract_diff, selector_key, junit_outcomes, all_passed, normalize_official_selector, observed_bug_failures
except ImportError:
    from repair_eval_common import sha, patch_paths, extract_diff, selector_key, junit_outcomes, all_passed, normalize_official_selector, observed_bug_failures

ROOT = Path('/testbed')
OUT = Path('/tmp/svaga-generated-evaluation')


def run(args, timeout=600, **kwargs):
    return subprocess.run(args, cwd=str(ROOT), text=True, encoding='utf-8', errors='replace', capture_output=True, timeout=timeout, **kwargs)


def checked(args):
    result = run(args)
    if result.returncode:
        raise RuntimeError('Command failed: ' + repr(args) + '\n' + result.stdout[-3000:] + result.stderr[-3000:])
    return result.stdout.strip()


def test_stage(name, selectors, timeout):
    xml = OUT/(name + '.xml')
    env = dict(os.environ, PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ.get('PATH', ''),
               PYTHONPYCACHEPREFIX=str(OUT.parent/('svaga-bytecode-' + OUT.name + '-' + name)))
    try:
        result = run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                      '--junitxml=' + str(xml), *selectors], timeout=timeout, env=env)
        output = result.stdout + '\n' + result.stderr
        code = result.returncode
    except subprocess.TimeoutExpired as error:
        output = 'Test execution timed out.\n' + str(error)
        code = 124
    (OUT/(name + '.log')).write_text(output, encoding='utf-8')
    try:
        outcomes = junit_outcomes(xml) if xml.exists() else {}
    except Exception as error:
        # Malformed/missing evidence must never be treated as success.
        outcomes = {}
        output += '\nJUnit parse error: ' + str(error)
        code = code or 125
    stage = {'stage': name, 'exit_code': code, 'outcomes': outcomes}
    print(name, 'exit', code, 'tests', len(outcomes), flush=True)
    return stage


def evaluate(task, candidate):
    allowed = sorted(patch_paths(task['patch']))
    if allowed != sorted(task['allowed_paths']):
        raise ValueError('Task allowed-file metadata mismatch')
    original_selectors = task['FAIL_TO_PASS'] + task['PASS_TO_PASS']
    selectors = [normalize_official_selector(s, task['repo']) for s in original_selectors]
    for selector in selectors:
        test_file = (ROOT/selector.split('::')[0]).resolve()
        if not test_file.is_relative_to(ROOT) or not test_file.is_file():
            raise ValueError('Official test path unavailable in image: ' + selector)
    expected = [selector_key(s) for s in selectors]
    fail_keys = [selector_key(normalize_official_selector(s, task['repo'])) for s in task['FAIL_TO_PASS']]
    pass_keys = [selector_key(normalize_official_selector(s, task['repo'])) for s in task['PASS_TO_PASS']]
    if not fail_keys or len(set(expected)) != len(expected):
        raise ValueError('Missing/duplicate explicit test identities')
    if checked(['git', 'status', '--porcelain']):
        raise ValueError('Official image starts dirty')
    blobs = {}
    for section in task['patch'].split('diff --git ')[1:]:
        header = re.match(r'a/(\S+) b/(\S+)\nindex ([0-9a-f]+)\.\.([0-9a-f]+)', section)
        if not header or header[1] != header[2] or header[1] not in allowed:
            raise ValueError('Unsupported official patch header')
        blob = checked(['git', 'hash-object', header[1]])
        if not blob.startswith(header[3]):
            raise ValueError('Official image/pre-bug source mismatch')
        blobs[header[1]] = blob
    if set(blobs) != set(allowed):
        raise ValueError('Incomplete official source verification')
    report = {'instance_id': task['instance_id'], 'variant': candidate['variant'],
              'environment_valid': False, 'candidate_passed': False, 'format_valid': False, 'patch_applies': False, 'stages': [],
              'verified_pre_bug_blobs': blobs, 'expected_tests': len(expected),
              'source_revision': task['source_revision'], 'protocol_version': 'repair-dev20-execution-v2',
              'selector_mapping': {a: b for a, b in zip(original_selectors, selectors) if a != b},
              'scope': 'development generated-patch execution, not external benchmark or security certification'}
    timeout = int(task.get('test_timeout_seconds', 600))
    clean = test_stage('clean_reference', selectors, timeout); report['stages'].append(clean)
    if not all_passed(clean, expected):
        report['status'] = 'invalid_clean_reference'; return report
    patch = OUT/'official_bug.patch'
    patch.write_bytes(task['patch'].encode('utf-8'))
    checked(['git', 'apply', '--check', str(patch)]); checked(['git', 'apply', str(patch)])
    buggy = test_stage('buggy_reference', selectors, timeout); report['stages'].append(buggy)
    try:
        observed_fail_keys = observed_bug_failures(buggy, fail_keys, pass_keys)
    except ValueError as error:
        report['status'] = 'invalid_buggy_reference'; report['detail'] = str(error); return report
    report['upstream_fail_to_pass_total'] = len(fail_keys)
    report['observed_fail_to_pass_total'] = len(observed_fail_keys)
    report['upstream_f2p_already_passing'] = [key for key in fail_keys if key not in observed_fail_keys]
    report['strict_upstream_f2p_reproduced'] = len(observed_fail_keys) == len(fail_keys)
    checked(['git', 'apply', '--reverse', str(patch)])
    restored = test_stage('restored_reference', selectors, timeout); report['stages'].append(restored)
    if not all_passed(restored, expected) or checked(['git', 'diff', '--name-only']):
        report['status'] = 'invalid_restored_reference'; return report
    checked(['git', 'apply', str(patch)])
    patch.unlink()  # Do not leave an oracle patch file beside executing generated source.
    report['environment_valid'] = True
    report['generation_seconds'] = candidate.get('seconds')
    report['output_tokens'] = candidate.get('output_tokens')
    if candidate.get('hit_token_limit'):
        report['status'] = 'generation_limit'; return report
    try:
        diff = extract_diff(candidate['text'], allowed)
    except (ValueError, KeyError) as error:
        report['status'] = 'invalid_diff'; report['detail'] = str(error); return report
    report['format_valid'] = True
    generated = OUT/'generated.patch'; generated.write_bytes(diff.encode('utf-8'))
    check = run(['git', 'apply', '--check', str(generated)])
    if check.returncode:
        report['status'] = 'patch_does_not_apply'; report['detail'] = check.stderr[-3000:]; return report
    checked(['git', 'apply', str(generated)])
    report['patch_applies'] = True
    dirty = set(checked(['git', 'diff', '--name-only']).splitlines())
    if not dirty <= set(allowed):
        report['status'] = 'protected_file_modified'; return report
    actual = test_stage('generated_repair', selectors, timeout); report['stages'].append(actual)
    dirty = set(checked(['git', 'diff', '--name-only']).splitlines())
    protected_unchanged = dirty <= set(allowed)
    report['fail_to_pass_restored'] = sum(actual['outcomes'].get(k) == 'passed' for k in observed_fail_keys)
    report['fail_to_pass_total'] = len(observed_fail_keys)
    report['pass_to_pass_preserved'] = sum(actual['outcomes'].get(k) == 'passed' for k in pass_keys)
    report['pass_to_pass_total'] = len(pass_keys)
    report['candidate_passed'] = all_passed(actual, expected) and protected_unchanged
    report['status'] = ('passed' if report['candidate_passed'] else 'protected_file_modified' if not protected_unchanged
                        else 'test_timeout' if actual['exit_code'] == 124 else 'tests_failed')
    return report


def main():
    assert ROOT == Path('/testbed') and (ROOT/'.git').exists()
    OUT.mkdir(exist_ok=False)
    source = Path('/tmp/svaga-eval-task.json')
    payload = json.loads(source.read_text(encoding='utf-8')); source.unlink()
    task, candidate = payload['task'], payload['candidate']
    try:
        report = evaluate(task, candidate)
    except Exception as error:
        report = {'instance_id': task['instance_id'], 'variant': candidate['variant'],
                  'environment_valid': False, 'candidate_passed': False,
                  'status': 'execution_error', 'detail': type(error).__name__ + ': ' + str(error)}
    (OUT/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('RESULT', report['status'], flush=True)


if __name__ == '__main__':
    main()
