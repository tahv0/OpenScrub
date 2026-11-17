"""Process-log delivery through the real portable runner, without Node/timing.

Only the external child boundary is controlled. Fresh-root configuration,
source/hash checks, the synthetic HTTP fixture, persistence and cleanup run.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]

CONTROLLED_CHILD = r"""
import os
from pathlib import Path
import runpy
import subprocess
import sys

runner, mode, scratch = sys.argv[1:4]
arguments = sys.argv[4:]
sys.path.insert(0, str(Path(runner).parent))

def child(command, **kwargs):
    assert Path(command[1]) == Path(runner).with_suffix('.js'), command
    log = Path(scratch) / 'logs' / 'measurement-candidate-timing.log'
    assert log.parent.is_dir(), 'process-log directory must exist before the controlled child executes'
    print('CONTROLLED_CHILD_LOG_PARENT_EXISTS', flush=True)
    if mode == 'timeout':
        raise subprocess.TimeoutExpired(command, kwargs['timeout'],
                                        output=b'timeout stdout\xff\n', stderr=b'timeout stderr\n')
    return subprocess.CompletedProcess(command, 0 if mode == 'success' else 7,
                                       stdout='synthetic stdout\n', stderr='synthetic stderr\n')

subprocess.run = child
sys.argv = [runner] + arguments
runpy.run_path(runner, run_name='__main__')
"""


@pytest.mark.parametrize('mode', ['success', 'nonzero', 'timeout'])
def test_fresh_process_log_directory_and_success_failure_diagnostics(tmp_path, mode):
    # Removing runner-owned mkdir must fail before the controlled child executes;
    # dropping either output stream or masking TimeoutExpired must also fail.
    scratch = tmp_path / 'fresh-root'
    scratch.mkdir()
    assert not (scratch / 'logs').exists()
    driver = ROOT / 'benchmark' / 'browser_logs.py'
    python = Path(sys.executable).resolve()
    files = [ROOT / relative for relative in (
        'openscrub.py', 'openscrub_web.py', 'zones_ui.py',
        'openscrub_internal/__init__.py', 'openscrub_internal/job_logs.py',
        'tests/test_job_polling_browser.py',
        'benchmark/browser_logs.py', 'benchmark/browser_logs.js', 'benchmark/browser_logs_env.py',
    )] + [python]
    manifest = scratch / 'frozen.json'
    manifest.write_text(json.dumps({'sha256': {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files
    }}))
    wrapper = scratch / 'controlled_child.py'
    wrapper.write_text(CONTROLLED_CHILD)
    # Python stands in for both tool paths but is never executed as Node/Chromium.
    command = [sys.executable, str(wrapper), str(driver), mode, str(scratch),
               '--root', str(scratch), '--source', str(ROOT),
               '--node', str(python), '--chromium', str(python),
               '--manifest', str(manifest), '--granted-sha', hashlib.sha256(manifest.read_bytes()).hexdigest(),
               '--phase', 'timing', '--label', 'candidate']
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    env.pop('PYTEST_PLUGINS', None)  # Standalone isolation comes from the runner.
    result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=30)
    assert 'CONTROLLED_CHILD_LOG_PARENT_EXISTS' in result.stdout, result.stdout + result.stderr
    log = scratch / 'logs' / 'measurement-candidate-timing.log'
    assert log.is_file(), result.stdout + result.stderr
    assert 'FileNotFoundError' not in result.stderr
    if mode == 'timeout':
        assert result.returncode != 0
        assert 'subprocess.TimeoutExpired' in result.stderr
        assert log.read_text() == 'timeout stdout\ufffd\ntimeout stderr\n\nSUBPROCESS TIMEOUT\n'
    else:
        assert result.returncode == (0 if mode == 'success' else 7), result.stdout + result.stderr
        assert log.read_text() == 'synthetic stdout\nsynthetic stderr\n'
        assert 'synthetic stdout' in result.stdout
        if mode == 'nonzero':
            assert 'synthetic stderr' in result.stderr
