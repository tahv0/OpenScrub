"""Validate helper records for exactly one unchanged JSON-only OpenCV probe."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

@pytest.fixture(autouse=True)
def exact_opencv_probe_stdout(request, monkeypatch):
    if request.node.name != 'test_real_compatible_runtime_has_required_fallback':
        yield
        return
    from openscrub_internal import opencv_compat
    cfg = json.loads(Path(os.environ['VERIFY_CONFIG']).read_text())
    source, root = Path(cfg['source']), Path(os.environ['VERIFY_RUN'])
    relative = 'openscrub_internal/opencv_compat.py'
    assert hashlib.sha256((source/relative).read_bytes()).hexdigest() == cfg['files'][relative]
    test = source/'tests/test_opencv_compat.py'
    assert hashlib.sha256(test.read_bytes()).hexdigest() == cfg['files']['tests/test_opencv_compat.py']
    actual_run = subprocess.run
    calls = []
    def run(args, *positional, **kwargs):
        result = actual_run(args, *positional, **kwargs)
        if args != [sys.executable, '-c', opencv_compat._PROBE]:
            return result
        assert not calls and not positional
        calls.append(True)
        assert kwargs == dict(capture_output=True, text=True, timeout=15)
        (root/'logs/opencv-probe-child.stdout').write_text(result.stdout)
        (root/'logs/opencv-probe-child.stderr').write_text(result.stderr)
        assert result.returncode == 0
        lines = result.stdout.splitlines(keepends=True)
        assert len(lines) >= 3 and lines[0].startswith('DEFAULT_PATHS ') and lines[1].startswith('ACTIVE_SOURCE ')
        assert json.loads(lines[0][len('DEFAULT_PATHS '):]) == {'jobs':str(source/'openscrub_jobs'),'models':str(root/'profile/.openscrub/models')}
        assert json.loads(lines[1][len('ACTIVE_SOURCE '):]) == {'executable':cfg['python'],'python':sys.version,
            'sources':{name:{'file':str(source/relative),'sha256':cfg['files'][relative]} for name,relative in cfg['modules'].items()}}
        payload=''.join(lines[2:])
        assert set(json.loads(payload)) == {'status','version','path','distributions','capability','detail'}
        (root/'logs/opencv-probe-adapter.json').write_text(json.dumps({'test':request.node.name,'exit':result.returncode,
          'probe_sha256':hashlib.sha256(opencv_compat._PROBE.encode()).hexdigest(),
          'stdout_sha256':hashlib.sha256(result.stdout.encode()).hexdigest(),
          'stderr_sha256':hashlib.sha256(result.stderr.encode()).hexdigest(),
          'verified_records':['DEFAULT_PATHS','ACTIVE_SOURCE']},indent=2)+'\n')
        return subprocess.CompletedProcess(result.args,result.returncode,payload,result.stderr)
    monkeypatch.setattr(subprocess,'run',run)
    yield
    assert calls == [True]
