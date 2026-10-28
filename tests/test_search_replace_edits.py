import subprocess
import pytest
from training.search_replace_edits import EditError, parse_edits, plan_edits, render_diff, reference_block


def block(search='old\n',replacement='new\n',path='src/app.py'):
    return path+'\n<<<<<<< SEARCH\n'+search+'=======\n'+replacement+'>>>>>>> REPLACE\n'


def make_source(root,content):
    (root/'src').mkdir();(root/'src/app.py').write_bytes(content)


def test_exact_match_renders_valid_patch_without_modifying_source(tmp_path):
    make_source(tmp_path,b'old\n')
    diff,matches=render_diff(tmp_path,block(),['src/app.py'])
    assert matches[0]['matches']==1 and '-old\n+new\n' in diff
    assert (tmp_path/'src/app.py').read_bytes()==b'old\n'
    subprocess.run(['git','-C',str(tmp_path),'init','-q'],capture_output=True,check=True)
    patch=tmp_path/'candidate.diff';patch.write_bytes(diff.encode())
    subprocess.run(['git','-C',str(tmp_path),'apply','--check',str(patch)],capture_output=True,check=True)


@pytest.mark.parametrize('content,search,code',[(b'old\nold\n','old\n','search_ambiguous'),
    (b'old\nold\nold\n','old\nold\n','search_ambiguous'),(b'old\n','OLD\n','search_not_found'),(b'    old\n','old\n','search_not_found')])
def test_no_case_or_indentation_fuzz_and_no_ambiguous_edit(tmp_path,content,search,code):
    make_source(tmp_path,content)
    with pytest.raises(EditError) as error:render_diff(tmp_path,block(search=search),['src/app.py'])
    assert error.value.code==code and (tmp_path/'src/app.py').read_bytes()==content


def test_multi_edit_failure_is_atomic_and_deletion_is_supported(tmp_path):
    make_source(tmp_path,b'old\nkeep\n')
    with pytest.raises(EditError):render_diff(tmp_path,block()+block('missing\n'),['src/app.py'])
    assert (tmp_path/'src/app.py').read_bytes()==b'old\nkeep\n'
    diff,_=render_diff(tmp_path,block(replacement=''),['src/app.py'])
    assert '-old\n' in diff


@pytest.mark.parametrize('text,code',[(block(path='../escape.py'),'disallowed_file'),
    (block(path='tests/test_app.py'),'disallowed_file'),(block(search='\n'),'empty_search'),
    (block().replace('>>>>>>> REPLACE',''),'invalid_edit_format')])
def test_format_and_path_guards(text,code):
    with pytest.raises(EditError) as error:parse_edits(text,['src/app.py'])
    assert error.value.code==code


def test_no_op_is_not_counted_as_an_applied_fix(tmp_path):
    make_source(tmp_path,b'old\n')
    with pytest.raises(EditError) as error:render_diff(tmp_path,block(replacement='old\n'),['src/app.py'])
    assert error.value.code=='no_effect'


def test_reference_generation_roundtrips_exact_bytes_and_whitespace(tmp_path):
    buggy='def f():\n    return 0\n\ndef g():\n    return 2\n'
    clean=buggy.replace('return 0','return 1')
    make_source(tmp_path,buggy.encode())
    text=reference_block('src/app.py',buggy,clean)
    edits=parse_edits(text,['src/app.py']);old,new,matches=plan_edits(tmp_path,edits)
    assert new['src/app.py']==clean.encode() and old['src/app.py']==buggy.encode()



@pytest.mark.parametrize('mode', ['correct','incorrect','missing_search'])
def test_exact_edit_adapter_executes_authored_fixture_and_preserves_test_controls(tmp_path,monkeypatch,mode):
    # This source is authored test code, not downloaded/model-generated code.
    from training import repair_eval_container as frozen
    from training.run_search_replace_eval import install_edit_adapter,annotate_report
    repository=tmp_path/'repository';repository.mkdir();(repository/'tests').mkdir()
    evidence=tmp_path/'evidence';evidence.mkdir()
    clean='def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n'
    tests='from app import add, multiply\n\ndef test_add():\n    assert add(2, 3) == 5\n\ndef test_multiply():\n    assert multiply(2, 3) == 6\n'
    (repository/'app.py').write_bytes(clean.encode());(repository/'tests/test_app.py').write_bytes(tests.encode())
    def git(*args):return subprocess.run(['git','-C',str(repository),*args],capture_output=True,text=True,check=True).stdout
    git('init','-q');git('config','core.autocrlf','false');git('config','core.eol','lf')
    git('add','app.py','tests/test_app.py')
    git('-c','user.name=Authored Test','-c','user.email=test@example.invalid','-c','commit.gpgsign=false','commit','-qm','clean authored source')
    (repository/'app.py').write_bytes(clean.replace('return a + b','return a - b').encode())
    bug=git('diff','--','app.py');git('checkout','--','app.py')
    task={'instance_id':'authored-search-replace','repo':'authored/fixture','source_revision':'test','patch':bug,
          'allowed_paths':['app.py'],'FAIL_TO_PASS':['tests/test_app.py::test_add'],
          'PASS_TO_PASS':['tests/test_app.py::test_multiply'],'test_timeout_seconds':30}
    search='    return a - b\n' if mode!='missing_search' else '    return missing_value\n'
    replacement='    return a + b\n' if mode=='correct' else '    return a * b\n'
    candidate={'variant':'adapter','text':block(search,replacement,'app.py'),'hit_token_limit':False}
    monkeypatch.setattr(frozen,'ROOT',repository);monkeypatch.setattr(frozen,'OUT',evidence)
    monkeypatch.setattr(frozen,'checked',frozen.checked);monkeypatch.setattr(frozen,'extract_diff',frozen.extract_diff)
    monkeypatch.setenv('PYTEST_DISABLE_PLUGIN_AUTOLOAD','1')
    metadata,application=install_edit_adapter(frozen)
    report=annotate_report(frozen.evaluate(task,candidate),metadata,application)
    assert report['environment_valid'] is True
    expected={'correct':'passed','incorrect':'tests_failed','missing_search':'search_not_found'}
    assert report['status']==expected[mode],report
    assert report['candidate_passed'] is (mode=='correct')
    if mode!='missing_search':assert report['pass_to_pass_preserved']==report['pass_to_pass_total']==1
    assert report['fuzzy_matching'] is False and report['reference_answer_used_for_generated_edit'] is False
