"""Run the actual setup page through Chromium and local job admission."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_optional_plate_setup_real_page_and_admission(tmp_path):
    if not all(os.environ.get(k) for k in ('OPENSCRUB_PLAYWRIGHT_MODULE', 'OPENSCRUB_CHROMIUM')) or not shutil.which('node'):
        pytest.skip('Existing Playwright and Chromium paths are required')
    artifacts = Path(os.environ.get('OPENSCRUB_POLICY_ARTIFACTS', str(tmp_path)))
    artifacts.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = 'http://127.0.0.1:%d' % port
    env = os.environ.copy()
    with (artifacts / 'server.log').open('w') as log:
        server = subprocess.Popen([sys.executable, str(ROOT / 'tests/optional_plate_setup_server.py'),
                                   str(ROOT), str(artifacts / 'runtime'), str(port)],
                                  cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(150):
                if server.poll() is not None:
                    pytest.fail((artifacts / 'server.log').read_text())
                try:
                    urllib.request.urlopen(url + '/api/jobs', timeout=.5).close()
                    break
                except OSError:
                    time.sleep(.1)
            else:
                pytest.fail('fixture server did not start')
            run = subprocess.run(['node', str(ROOT / 'tests/optional_plate_setup_browser.cjs'),
                                  url, str(artifacts)], env=env, capture_output=True, text=True, timeout=120)
            (artifacts / 'browser.log').write_text(run.stdout + run.stderr)
            assert run.returncode == 0, run.stdout + run.stderr
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
