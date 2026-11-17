import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace

SOURCE = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
sys.path.insert(0, str(SOURCE))
import baseline_isolation
web = baseline_isolation.configure('task61-http')
import openscrub as engine
from openscrub_internal import reports
import cv2
import numpy as np
from werkzeug.serving import make_server

root = Path('/tmp/openscrub-task61/runtime')
root.mkdir(exist_ok=True)
jobs = root / 'jobs'
folder = jobs / 'synthetic'
folder.mkdir(parents=True, exist_ok=True)
video = folder / 'input.avi'
path = folder / 'report.json'
web.JOBS_DIR = str(jobs)
web.TOKEN = None
web.JOBS.clear()
if '--reopen' in sys.argv:
    web.rehydrate_jobs()
    response = web.app.test_client().get('/api/jobs/synthetic/detections')
    assert response.status_code == 200
    assert web.JOBS['synthetic']['phase'] == 'review'
    print(json.dumps({'restart_phase': 'review', 'restart_get_status': 200}))
    sys.exit()
writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'MJPG'), 30, (160, 96))
assert writer.isOpened()
for i in range(60):
    frame = np.full((96, 160, 3), 50 + i * 2, np.uint8)
    cv2.putText(frame, str(i), (70, 50), cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 0, 0), 1)
    writer.write(frame)
writer.release()
parser = engine.build_parser()
scan = parser.parse_args([str(video), '--categories', 'manual', '--report', str(path)])
state = engine.run_scan(scan)
engine.write_report(path, scan, state)
scan_doc = json.loads(path.read_bytes())
assert scan_doc['detections'] == []
web.JOBS['synthetic'] = {'dir': str(folder), 'video': str(video), 'log': []}
web.app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)
server = make_server('127.0.0.1', 0, web.app, threaded=True)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
url = 'http://127.0.0.1:%s/api/jobs/synthetic/detections' % server.server_port
original = reports.json
results = {'scan': 'manual-only synthetic scan completed', 'http_failures': {}}
try:
    for failure in ('encoding', 'write'):
        previous = path.read_bytes()
        def fail(doc, stream, **kwargs):
            if failure == 'write':
                stream.write('{"interrupted":')
                raise OSError('injected HTTP write failure')
            raise TypeError('injected HTTP encoding failure')
        reports.json = SimpleNamespace(dump=fail)
        req = urllib.request.Request(url, data=b'{"enabled": {}}', headers={'Content-Type': 'application/json'})
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError('HTTP failure was acknowledged')
        except urllib.error.HTTPError as exc:
            assert exc.code == 500
        finally:
            reports.json = original
        assert path.read_bytes() == previous
        assert not list(folder.glob('*.tmp'))
        child = subprocess.run([sys.executable, __file__, '--reopen'], capture_output=True, text=True, check=True)
        results['http_failures'][failure] = {'status': 500, 'bytes_preserved': True,
                                            'restart': json.loads(child.stdout.splitlines()[-1])}
    payload = {'manual': [{'t_start': 0, 't_end': 1, 'screen_box': [10, 10, 30, 30]}]}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=5) as response:
        ack = json.load(response)
    assert ack == {'ok': True, 'total': 1, 'suggest_allowlist': []}
    assert json.loads(path.read_bytes())['detections'][0]['category'] == 'manual'
    results['http_success'] = ack
finally:
    reports.json = original
    server.shutdown()
    thread.join(5)
    server.server_close()
output = folder / 'rendered.mp4'
args = parser.parse_args([str(video), '--from-report', str(path), '--report', str(path),
                          '--output', str(output), '--encoder', 'x264'])
engine.run_pipeline(args)
cap = cv2.VideoCapture(str(output))
frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
cap.release()
assert frames == 60 and len(json.loads(path.read_bytes())['detections']) == 1
results['render'] = {'frames': frames, 'report_rows': 1, 'output_bytes': output.stat().st_size}
(root.parent / 'runtime-results.json').write_text(json.dumps(results, indent=2))
print(json.dumps(results, indent=2))
