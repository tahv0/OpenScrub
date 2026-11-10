"""Exercise real child interpreters with intentionally conflicting server packages.

Tiny dependency fixtures replace GPU libraries; these are launch/isolation tests,
not CUDA training tests. The user supplied the real RTX 3080 A/B reproduction.
"""
import builtins
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import venv

import pytest
import learning_session as ls
from scripts import train_plate_seg as trainer


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    env = tmp_path / 'training venv'
    venv.EnvBuilder(with_pip=False).create(env)
    python = env / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    site = Path(subprocess.check_output(
        [str(python), '-I', '-c', 'import sysconfig;print(sysconfig.get_path("purelib"))'],
        text=True).strip())
    for name in ('cv2', 'numpy', 'ultralytics', 'onnx', 'onnxruntime'):
        (site / (name + '.py')).write_text('ORIGIN = "training"\n')
    (site / 'torch.py').write_text('''from types import SimpleNamespace
__version__ = 'fixture-cuda'
version = SimpleNamespace(cuda='fixture')
cuda = SimpleNamespace(is_available=lambda: True, device_count=lambda: 1,
                       get_device_name=lambda device: 'fixture GPU')
''')
    server = tmp_path / 'server dist-packages'
    server.mkdir()
    script = server / 'openscrub_train_plate_seg.py'
    script.write_text(Path(trainer.__file__).read_text())
    for name in ('cv2', 'numpy', 'torch', 'ultralytics', 'onnx', 'onnxruntime'):
        (server / (name + '.py')).write_text(
            'raise ImportError("server library conflict: ncclCommShrink")\n')
    cwd = tmp_path / 'unrelated working directory'
    cwd.mkdir()
    (cwd / 'torch.py').write_text('raise ImportError("wrong working directory torch")\n')
    weights = tmp_path / 'trusted.pt'
    weights.write_bytes(b'fixture, never unpickled')
    monkeypatch.chdir(cwd)
    monkeypatch.setenv('PYTHONPATH', str(server))
    monkeypatch.setenv('OPENSCRUB_TRAIN_PYTHON', str(python))
    monkeypatch.setenv('OPENSCRUB_TRAIN_WEIGHTS', str(weights))
    monkeypatch.setattr(ls, 'trainer_script', lambda: script)
    return python, site, script, weights


def test_packaged_preflight_ignores_server_and_working_directory_packages(runtime):
    python, _, script, _ = runtime
    result = ls.preflight()
    assert result['ready'], result['problems']
    assert result['python'] == str(python)
    assert result['script'] == str(script)


def test_preflight_loads_actual_trainer_before_optional_imports(runtime):
    _, site, _, _ = runtime
    # Loose import torch... used to pass even if the trainer's first import failed.
    (site / 'cv2.py').write_text('raise ImportError("training cv2 dependency broken")\n')
    result = ls.preflight()
    assert not result['ready']
    assert 'training cv2 dependency broken' in '\n'.join(result['problems'])


def test_preflight_still_requires_cuda_and_never_uses_cpu(runtime):
    _, site, _, _ = runtime
    (site / 'torch.py').write_text('''from types import SimpleNamespace
__version__ = 'fixture-cpu'
version = SimpleNamespace(cuda=None)
cuda = SimpleNamespace(is_available=lambda: False)
''')
    result = ls.preflight()
    assert not result['ready']
    assert 'CPU fallback is forbidden' in '\n'.join(result['problems'])


def test_preflight_retains_underlying_library_error(runtime):
    _, site, _, _ = runtime
    (site / 'torch.py').write_text('raise ImportError("libtorch_cuda.so: undefined symbol: ncclCommShrink")\n')
    result = ls.preflight()
    assert not result['ready']
    assert 'ncclCommShrink' in '\n'.join(result['problems'])


def test_real_training_child_is_isolated_unbuffered_and_accepts_space_paths(runtime, tmp_path):
    python, _, script, weights = runtime
    # Keep run_training's real Popen/log/artifact-check path. No GPU is simulated
    # as a training result: this child publishes only explicit fixture bytes.
    script.write_text('''import hashlib, json, sys
from pathlib import Path
import numpy, torch
assert numpy.ORIGIN == 'training'
assert sys.flags.isolated == 1
assert sys.stdout.write_through
assert sys.argv[1] == 'train'
root = Path(sys.argv[sys.argv.index('--versions-dir') + 1])
folder = root / 'vfixture'
folder.mkdir()
artifacts = {}
for name in ('weights.pt', 'model.onnx'):
    data = b'fixture, not a model'
    (folder / name).write_bytes(data)
    artifacts[name] = hashlib.sha256(data).hexdigest()
(folder / 'manifest.json').write_text(json.dumps({'artifacts': artifacts}))
(root / 'index.json').write_text(json.dumps({'versions':[{'version':'vfixture'}]}))
print('isolated training child fixture reached')
''')
    folder, meta = ls.run_training(tmp_path / 'dataset path', tmp_path / 'pass' / 'versions',
                                   weights, {'cancel': threading.Event(), 'log': []}, {})
    assert folder.name == 'vfixture'
    assert set(meta['artifacts']) == {'weights.pt', 'model.onnx'}
    assert 'isolated training child fixture reached' in (folder.parent.parent / 'training.log').read_text()


@pytest.mark.parametrize('failure', [
    ImportError('libtorch_cuda.so: undefined symbol: ncclCommShrink'),
    OSError('libcudnn.so: cannot open shared object file'),
    ModuleNotFoundError("No module named 'torch'"),
])
def test_cuda_check_preserves_exception_and_selected_interpreter(monkeypatch, failure):
    original = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if name == 'torch':
            raise failure
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded_import)
    with pytest.raises(RuntimeError) as error:
        trainer._cuda_info(0)
    assert str(failure) in str(error.value)
    assert sys.executable in str(error.value)
    assert error.value.__cause__ is failure


def test_preflight_cli_needs_no_dataset_weights_or_license(runtime):
    python, _, script, _ = runtime
    result = subprocess.run([str(python), '-I', '-u', str(script), 'preflight'],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data['gpu'] == 'fixture GPU'
    assert data['python'] == str(python)
    assert data['isolated'] is True


def test_missing_checkpoint_is_still_rejected(runtime):
    _, _, _, weights = runtime
    weights.unlink()
    result = ls.preflight()
    assert not result['ready']
    assert len(result['problems']) == 1, result['problems']
    assert 'checkpoint' in result['problems'][0]


def test_preflight_checks_export_dependencies_too(runtime):
    _, site, _, _ = runtime
    (site / 'onnxruntime.py').write_text('raise ImportError("ONNX runtime dependency broken")\n')
    result = ls.preflight()
    assert not result['ready']
    assert 'ONNX runtime dependency broken' in '\n'.join(result['problems'])
