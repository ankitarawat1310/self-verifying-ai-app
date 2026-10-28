"""Audit saved paired executable evidence without executing generated code or rerunning tests."""
import argparse
import csv
import json
from pathlib import Path
from repair_eval_common import sha, selector_key, normalize_official_selector, all_passed, observed_bug_failures, junit_outcomes, extract_diff
from run_repair_eval import validate_predictions, summarize


def audit(packet, folder):
    manifest, tasks, predictions = validate_predictions(packet, folder/'generation_results.json')
    provenance = json.loads((folder/'provenance.json').read_text())
    assert provenance['tasks_requested'] == 20
    assert provenance['predictions_sha256'] == sha((folder/'generation_results.json').read_bytes())
    assert provenance['packet_manifest_sha256'] == sha((packet/'public/manifest.json').read_bytes())
    assert (folder/'packet_manifest.json').read_bytes() == (packet/'public/manifest.json').read_bytes()
    for name, digest in provenance['evaluator_sources_sha256'].items():
        assert sha((folder/'evaluator-sources'/name).read_bytes()) == digest, name
    rows = json.loads((folder/'reports.json').read_text())
    lookup = {(r['instance_id'], r['variant']): r for r in rows}
    assert len(rows) == len(lookup) == 40 and set(lookup) == set(predictions)
    stages_checked = 0
    for task in tasks:
        fail = [selector_key(normalize_official_selector(s, task['repo'])) for s in task['FAIL_TO_PASS']]
        passed = [selector_key(normalize_official_selector(s, task['repo'])) for s in task['PASS_TO_PASS']]
        expected = set(fail + passed)
        for variant in manifest['variants']:
            key = (task['instance_id'], variant)
            row = lookup[key]
            attempt = (folder/row['attempt_directory']).resolve()
            assert attempt.is_relative_to(folder.resolve())
            evidence = attempt/'evidence'
            original = json.loads((evidence/'report.json').read_text())
            assert all(row[k] == value for k, value in original.items())
            stages = {s['stage']: s for s in row.get('stages', [])}
            assert len(stages) == len(row.get('stages', []))
            for name, stage in stages.items():
                assert junit_outcomes(evidence/(name+'.xml')) == stage['outcomes'], (key, name)
                assert (evidence/(name+'.log')).is_file()
                stages_checked += 1
            if not row['environment_valid']:
                assert not row['candidate_passed']
                continue
            assert all_passed(stages['clean_reference'], expected)
            observed = observed_bug_failures(stages['buggy_reference'], fail, passed)
            assert all_passed(stages['restored_reference'], expected)
            assert row['expected_tests'] == len(expected)
            assert row['observed_fail_to_pass_total'] == len(observed)
            assert row['strict_upstream_f2p_reproduced'] == (len(observed) == len(fail))
            if row['format_valid']:
                raw = extract_diff(predictions[key]['text'], task['allowed_paths'])
                assert (evidence/'generated.patch').read_bytes() == raw.encode('utf-8')
            if row['patch_applies']:
                generated = stages['generated_repair']
                assert row['fail_to_pass_restored'] == sum(generated['outcomes'].get(k) == 'passed' for k in observed)
                assert row['pass_to_pass_preserved'] == sum(generated['outcomes'].get(k) == 'passed' for k in passed)
                assert row['fail_to_pass_total'] == len(observed)
                assert row['pass_to_pass_total'] == len(passed)
            if row['candidate_passed']:
                assert row['status'] == 'passed' and row['format_valid'] and row['patch_applies']
                assert all_passed(stages['generated_repair'], expected)
                assert row['fail_to_pass_restored'] == len(observed)
                assert row['pass_to_pass_preserved'] == len(passed)
    saved = json.loads((folder/'summary.json').read_text())
    recomputed = summarize(rows, 20)
    for k, value in recomputed.items():
        if k != 'protocol_version': assert saved[k] == value, k
    assert saved['comparison_complete'] is True and saved['completed_variant_records'] == 40
    comparison = []
    counts = dict(both_pass=0, adapter_only_pass=0, base_only_pass=0, neither_pass=0, invalid_pair=0)
    for task in tasks:
        b, a = (lookup[(task['instance_id'], v)] for v in ['base', 'adapter'])
        valid = b['environment_valid'] and a['environment_valid']
        label = ('both_pass' if b['candidate_passed'] and a['candidate_passed'] else 'adapter_only_pass' if a['candidate_passed'] else 'base_only_pass' if b['candidate_passed'] else 'neither_pass') if valid else 'invalid_pair'
        counts[label] += 1
        comparison.append(dict(instance_id=task['instance_id'], paired_environment_valid=valid, base_status=b['status'], adapter_status=a['status'], outcome=label))
    report = dict(scope='saved_evidence_audit_no_test_reruns', passed=True, variant_records=40, stages_with_matching_junit=stages_checked, paired_outcomes=counts,
        evidence_sha256={n:sha((folder/n).read_bytes()) for n in ['generation_results.json','packet_manifest.json','provenance.json','reports.json','summary.json']},
        limitations=['Development tasks with supplied affected locations; not Terminal-Bench or secure-application certification.', 'Strict numerical reload failure remains unresolved and unchanged.', 'A lower prediction loss is not a functional repair pass rate.'])
    with (folder/'verification.json').open('x', encoding='utf-8') as f: json.dump(report,f,indent=2)
    with (folder/'per_task_comparison.csv').open('x',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(comparison[0]));writer.writeheader();writer.writerows(comparison)
    lines=['# Qwen3-Coder-30B: frozen development repair comparison','', '20 frozen SWE-smith development tasks; unchanged prompts and outputs; official isolated Docker environments with clean, buggy and restored reference controls.','', '| Outcome | Base | Fine-tuned adapter |','|---|---:|---:|']
    for title, key in [('Fully passing repairs','passed'),('Format accepted','format_valid'),('Patches applied','patch_applies'),('Tasks with observed regressions','tasks_with_regressions')]:
        lines.append(f"| {title} | {saved['variants']['base'][key]}/20 | {saved['variants']['adapter'][key]}/20 |")
    lines += ['', 'Paired outcomes: '+json.dumps(counts)+'.','', 'All saved stage outcomes were checked against their JUnit XML. Input, evaluator-snapshot and generated-patch hashes/bytes were audited. See verification.json and per_task_comparison.csv.','', '## Interpretation','', 'These are development results for localized Python repair with affected files supplied. They do not establish full application correctness, security, Terminal-Bench performance or generalization to untouched tasks. The validation set has been inspected repeatedly.','', 'The earlier 67.12% dev100 prediction-loss reduction is a separate teacher-forced metric. The strict fresh-reload numerical comparison remains FAILED even though saved adapter, tokenizer and serialized frozen-base identities matched. No tolerance was loosened.','', 'One Trio task has 21 upstream fail-to-pass labels, of which 18 actually fail in the verified buggy environment; three already pass. This is recorded, and a generated repair must still pass all named tests. The other 19 tasks reproduce every listed failure.','', 'This comparison changes the adapter condition within the frozen 30B protocol. Comparisons with the earlier 1.5B run also differ in runtime, precision, adapter configuration and generation settings; they do not isolate model size alone.','', 'Next: complete the same-instance base/adapter prediction-loss comparison on all 1,000 development examples, preserve the outputs, review repair failures and plan the remaining required models plus the external benchmark.']
    with (folder/'analysis.md').open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
    print(json.dumps(report,indent=2))

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet',type=Path,required=True)
    parser.add_argument('--results',type=Path,required=True)
    args=parser.parse_args()
    audit(args.packet,args.results)
