"""Task16330 adapter: actual installed entry point/listening server, no benchmark."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
root = Path(os.environ['VERIFY_RUN'])
target = Path(sys.argv[1])
with socket.socket() as listener:
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
log = root / 'logs/listening-server.log'
log.parent.mkdir(parents=True, exist_ok=True)
with log.open('w') as output:
    proc = subprocess.Popen([sys.executable, str(target / 'bin/openscrub-web'), '--http', '--host', '127.0.0.1', '--port', str(port), '--retain-days', '0'], cwd=root, stdout=output, stderr=subprocess.STDOUT)
    try:
        base = 'http://127.0.0.1:' + str(port)
        for _ in range(100):
            try:
                with urllib.request.urlopen(base + '/api/jobs', timeout=2) as response:
                    jobs = json.load(response)
                break
            except urllib.error.URLError:
                assert proc.poll() is None, 'server exited; see listening-server.log'
                time.sleep(.1)
        else:
            raise AssertionError('server readiness deadline')
        assert jobs == [], jobs
        with urllib.request.urlopen(base + '/', timeout=3) as response:
            page = response.read().decode()
            assert response.status == 200 and 'OpenScrub' in page
        print(json.dumps({'server': 'actual installed openscrub-web', 'base': base, 'jobs': '200 empty', 'page': '200 OpenScrub'}, sort_keys=True))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        print('SERVER_CLEANUP', proc.returncode)
