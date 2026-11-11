"""Training is optional, isolated from runtime cv2, and uses a pinned checkpoint."""
import hashlib
import io
from pathlib import Path
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
