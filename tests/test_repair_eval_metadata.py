import pytest
from training.repair_eval_image_metadata import validate_packaging_status


def test_installed_text_metadata_is_preserved_and_hashed(tmp_path):
    folder=tmp_path/'package.egg-info';folder.mkdir();file=folder/'PKG-INFO';file.write_bytes(b'Package: authored fixture')
    before=file.read_bytes();rows=validate_packaging_status('?? package.egg-info/\n',tmp_path)
    assert len(rows)==1 and len(rows[0]['sha256'])==64 and file.read_bytes()==before


@pytest.mark.parametrize('status',[' M app.py','?? random.py','?? ../escape.egg-info/'])
def test_tracked_edits_and_other_untracked_paths_still_fail(tmp_path,status):
    with pytest.raises(ValueError):validate_packaging_status(status,tmp_path)


def test_executable_file_in_metadata_is_rejected(tmp_path):
    folder=tmp_path/'package.egg-info';folder.mkdir();(folder/'evil.py').write_text('authored fixture')
    with pytest.raises(ValueError):validate_packaging_status('?? package.egg-info/\n',tmp_path)



def test_path_prefix_level_is_derived_without_guessing_or_rewriting():
    from training.repair_eval_image_metadata import derived_strip_level
    assert derived_strip_level('--- a/src/app.py\n+++ b/src/app.py\n') == 1
    assert derived_strip_level('--- src/app.py.orig\t2023-01-01\n+++ src/app.py\t2023-01-01\n') == 0
    with pytest.raises(ValueError):
        derived_strip_level('--- a/src/app.py\n+++ b/src/app.py\n--- other.py\n+++ other.py\n')


def test_native_git_plain_nested_paths_need_strip_zero(tmp_path):
    import subprocess
    root=tmp_path/'repo';root.mkdir();(root/'src').mkdir();(root/'src/app.py').write_bytes(b'old\n')
    subprocess.run(['git','-C',str(root),'init','-q'],capture_output=True,check=True)
    patch=tmp_path/'patch.diff';patch.write_bytes(b'--- src/app.py.orig\n+++ src/app.py\n@@ -1 +1 @@\n-old\n+new\n')
    correct=subprocess.run(['git','-C',str(root),'apply','--check','-p0',str(patch)],capture_output=True)
    wrong=subprocess.run(['git','-C',str(root),'apply','--check','-p1',str(patch)],capture_output=True)
    assert correct.returncode==0 and wrong.returncode!=0
    assert (root/'src/app.py').read_bytes()==b'old\n'
