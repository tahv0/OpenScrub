"""Training is optional, isolated from runtime cv2, and uses a pinned checkpoint."""
import hashlib
import io
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import zipfile
import pytest
from scripts import download_training_checkpoint as checkpoint


def test_download_verifies_before_installing(tmp_path,monkeypatch):
    data=b'local fixture, not a pickle';path=tmp_path/'weights.pt'
    monkeypatch.setattr(checkpoint,'SHA256',hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(checkpoint,'urlopen',lambda *a,**k:io.BytesIO(data))
    assert checkpoint.download(path)==path and path.read_bytes()==data
    monkeypatch.setattr(checkpoint,'urlopen',lambda *a,**k:pytest.fail('existing verified checkpoint downloaded twice'))
    checkpoint.download(path)


def test_bad_checkpoint_is_not_installed_or_replaced(tmp_path,monkeypatch):
    path=tmp_path/'weights.pt'
    monkeypatch.setattr(checkpoint,'urlopen',lambda *a,**k:io.BytesIO(b'wrong content'))
    with pytest.raises(ValueError,match='SHA256'):checkpoint.download(path)
    assert not path.exists() and not list(tmp_path.iterdir())
    path.write_bytes(b'user-file')
    with pytest.raises(ValueError,match='NOT replaced'):checkpoint.download(path)
    assert path.read_bytes()==b'user-file'


def test_all_runtime_images_include_learning_imports():
    root=Path(__file__).parent
    for name in ('Dockerfile','Dockerfile.cuda','Dockerfile.intel'):
        text=(root/name).read_text()
        for module in ('stop_review.py','video_learning.py','learning_session.py','learned_models.py'):
            assert module in text,name+' omits '+module
        assert 'COPY scripts/ scripts/' in text
    cuda=(root/'Dockerfile.cuda').read_text()
    assert 'ARG OPENSCRUB_ENABLE_TRAINING=0' in cuda
    assert 'python3 -m venv /opt/openscrub-training' in cuda
    assert '/opt/openscrub-training/bin/python -m pip' in cuda
    assert 'torch==2.10.0 torchvision==0.25.0' in cuda


@pytest.fixture(scope='module')
def learning_distributions(tmp_path_factory):
    pytest.importorskip('build')
    pytest.importorskip('hatchling')
    destination = tmp_path_factory.mktemp('learning-distributions')
    result = subprocess.run([sys.executable, '-m', 'build', '--no-isolation',
                             '--outdir', str(destination)], cwd=Path(__file__).parent,
                            text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    return destination


def _import_secondary_modules(folder):
    # A fresh interpreter cannot accidentally reuse modules from the source tree.
    script = '''import pathlib,sys
root=pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root))
import plate_verifier,learning_candidates
assert pathlib.Path(plate_verifier.__file__).parent == root
assert pathlib.Path(learning_candidates.__file__).parent == root
assert callable(plate_verifier.review_report)
assert callable(learning_candidates.evaluate)
'''
    result = subprocess.run([sys.executable, '-I', '-c', script, str(folder)],
                            cwd=folder, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_installed_wheel_secondary_workflows_import_without_source_tree(learning_distributions, tmp_path):
    wheel = next(learning_distributions.glob('*.whl'))
    with zipfile.ZipFile(wheel) as package:
        package.extractall(tmp_path)
    _import_secondary_modules(tmp_path)


def test_sdist_contains_working_secondary_workflows(learning_distributions, tmp_path):
    with tarfile.open(next(learning_distributions.glob('*.tar.gz'))) as package:
        # This archive was built directly above from this repository, not supplied by a user.
        package.extractall(tmp_path, filter='data')
    source = next(path for path in tmp_path.iterdir() if path.is_dir())
    _import_secondary_modules(source)


@pytest.mark.parametrize('dockerfile', ['Dockerfile', 'Dockerfile.cuda', 'Dockerfile.intel'])
def test_container_application_copy_set_can_import_secondary_workflows(tmp_path, dockerfile):
    root = Path(__file__).parent
    logical_lines = (root / dockerfile).read_text().replace('\\\n', ' ').splitlines()
    app_copy = next(shlex.split(line)[1:-1] for line in logical_lines
                    if line.startswith('COPY ') and 'openscrub_web.py' in line)
    for relative in app_copy:
        shutil.copyfile(root / relative, tmp_path / Path(relative).name)
    _import_secondary_modules(tmp_path)
