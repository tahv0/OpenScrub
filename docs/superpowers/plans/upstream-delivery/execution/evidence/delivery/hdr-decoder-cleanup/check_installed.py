import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

art = Path('/tmp/openscrub-task109')
site = art / 'installed/site-packages'
profile = Path(tempfile.mkdtemp(prefix='installed-profile-', dir=art))
hooks = art / 'hooks'
env = dict(os.environ, PYTHONPATH=str(hooks) + ':' + str(site),
           OPENSCRUB_TASK109_PROFILE=str(profile), OPENSCRUB_NO_AUTOFETCH='1')
python = '/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python'
probe = subprocess.run([python, '-c', '''
from pathlib import Path
import inspect, json, openscrub, openscrub_web as web, zones_ui
site = Path('/tmp/openscrub-task109/installed/site-packages')
for module in (openscrub, web, zones_ui):
    assert Path(module.__file__).parent == site, module.__file__
assert Path(openscrub.render_hdr.__code__.co_filename).parent == site
args = openscrub.build_parser().parse_args(['synthetic.mp4'])
assert (args.engine,args.device,args.encoder,args.mode,args.pad,args.coverage,args.out_quality) == ('auto','auto','auto','blur',8,'tight','archival')
print(json.dumps({'engine':openscrub.__file__,'web':web.__file__,'jobs':web.JOBS_DIR}))
'''], cwd=art, env=env, text=True, capture_output=True, check=True)
assert str(profile) in probe.stdout
cli = subprocess.run([str(site / 'bin/openscrub'), '--help'], cwd=art, env=env,
                     text=True, capture_output=True, check=True)
assert 'usage:' in cli.stdout and 'video' in cli.stdout
(art / 'installed-cli-help.txt').write_text(cli.stdout)
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
with (art / 'installed-web.log').open('w') as log:
    process = subprocess.Popen([str(site / 'bin/openscrub-web'), '--http', '--host', '127.0.0.1',
                                '--port', str(port), '--retain-days', '0'], cwd=art, env=env,
                               stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 15
        while True:
            try:
                with urllib.request.urlopen('http://127.0.0.1:' + str(port) + '/api/jobs', timeout=3) as response:
                    assert response.status == 200 and json.load(response) == []
                break
            except (OSError, urllib.error.URLError):
                assert process.poll() is None, 'installed web exited before serving'
                if time.monotonic() > deadline:
                    raise
                time.sleep(.05)
        with urllib.request.urlopen('http://127.0.0.1:' + str(port) + '/', timeout=3) as response:
            assert response.status == 200 and b'OpenScrub' in response.read()
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
            raise AssertionError('installed server failed to stop')
assert process.returncode == 0
result = {'active_installed_sources': json.loads(probe.stdout), 'cli_help': True,
          'web_homepage_and_empty_jobs_http200': True, 'sigterm_rc': process.returncode,
          'clean_profile': str(profile), 'cli_defaults': 'unchanged'}
(art / 'installed-startup.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
