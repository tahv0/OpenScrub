"""Task-only native/installed HTTP and initializer work counts; no model."""
import copy
from fractions import Fraction
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import urllib.error
import urllib.request

import cv2
import numpy as np
from werkzeug.serving import make_server
import openscrub as engine
import openscrub_web as web

root = Path(os.environ['VERIFY_RUN'])
cfg = json.loads(Path(os.environ['VERIFY_CONFIG']).read_text())
web.TOKEN = None
manifest = json.loads(Path(os.environ['OPENSCRUB_EXACT_MEDIA']).read_text())
fixture = manifest['cfr5']
assert hashlib.sha256(Path(fixture['path']).read_bytes()).hexdigest() == fixture['sha256']
job = web.new_job('', {}, 'strict-native-five.mp4')
video = Path(job['dir']) / 'input.mp4'
shutil.copyfile(fixture['path'], video)
job.update(video=str(video), phase='review')
row = dict(t_start=0., t_end=2., last_seen=.5, cbox=[1, 2, 8, 9],
    aoff=[0, 0], category='manual', text='retained', confidence=.9,
    enabled=True, manual_id='http:immutable', manual_creation={'opaque': 'retain'},
    future={'keep': [None, False, 'snow']})
doc = dict(provenance=dict(input=str(video), settings={}),
    render_state=dict(fps=5, cum=[[i, -i] for i in range(10)], bands=[[0, 0]]*10),
    detections=[row, dict(row, enabled=False, text='disabled', track=17)],
    audio_redactions=[dict(t0=0., t1=.4, mode='mute')], future_top={'keep': True})
path = Path(job['dir']) / 'report.json'
path.write_text(json.dumps(doc))
# Independent sequential pixel and integer-PTS oracles, outside counted work.
refs = []
cap = cv2.VideoCapture(str(video))
try:
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        refs.append(frame)
        assert len(refs) <= 60
finally:
    cap.release()
probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams',
    'v:0', '-show_frames', '-show_entries', 'frame=pts:stream=time_base', '-of',
    'json', str(video)], timeout=15))
pts = [Fraction(frame['pts'])*Fraction(probe['streams'][0]['time_base'])
       for frame in probe['frames']]
assert len(refs) == len(pts) == 10 and pts[9] == Fraction(9, 5)

counts, captures, initializers, indexed, threads, bodies = {}, [], [], [], [], []
mode = 'strict'
def bump(key):
    counts[key] = counts.get(key, 0) + 1
def counted(owner, name, key):
    original = getattr(owner, name)
    def call(*args, **kwargs):
        bump(key)
        return original(*args, **kwargs)
    setattr(owner, name, call)
for owner, name, key in [
    (web, '_exact_snapshot', 'snapshots'), (web.exact, 'timeline', 'timeline_traversals'),
    (web, '_load_job_report', 'latest_raw_loads'),
    (web, '_read_exact_source', 'web_verifications'),
    (web, '_exact_current_locked', 'source_current_checks'),
    (web, '_report_committed_locked', 'committed_notifications')]:
    counted(owner, name, key)
real_capture = cv2.VideoCapture
class Capture:
    def __init__(self, *args):
        self.cap, self.releases, self.after_index = real_capture(*args), 0, None
        captures.append(self)
    def __getattr__(self, name):
        return getattr(self.cap, name)
    def release(self):
        self.after_index = self.cap.get(cv2.CAP_PROP_POS_FRAMES)
        self.releases += 1
        self.cap.release()
cv2.VideoCapture = Capture
real_read = web.exact.read_indexed_capture
def read(*args, **kwargs):
    bump('indexed_reads')
    result = real_read(*args, **kwargs)
    indexed.append(result)
    return result
web.exact.read_indexed_capture = read
def person(*args, **kwargs):
    if mode == 'strict':
        assert len(captures) == 1 and captures[0].releases == 1
    bump('person_resolutions')
    return None
engine.PersonDetector = person
class Tracker:
    def init(self, frame, box):
        bump('vit_initializers')
        initializers.append(frame.copy())
engine._vittrack_factory = lambda log: Tracker
real_start = web._start_owned_thread
def start(target, lease):
    thread = real_start(target, lease)
    threads.append(thread)
    return thread
web._start_owned_thread = start
@web.app.before_request
def record_body():
    if web.request.path.endswith('/track_object'):
        bodies.append(web.request.get_json())
def fetch(base, suffix, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base+suffix, data=data,
        headers={'Content-Type': 'application/json'})
    try:
        response = urllib.request.urlopen(req, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read())
def join():
    for thread in threads:
        thread.join(8)
        assert not thread.is_alive()
def reset():
    counts.clear(); captures.clear(); initializers.clear(); indexed.clear()

server = make_server('127.0.0.1', 0, web.app, threaded=True)
server_thread = threading.Thread(target=server.serve_forever)
server_thread.start()
base = 'http://127.0.0.1:'+str(server.server_port)
url = '/api/jobs/'+job['id']
results = {}
try:
    status, sample = fetch(base, url+'/edit_sample?t=1.9')
    assert status == 200 and sample['sample']['index'] == 9
    pc = {key: sample['sample'][key] for key in (
        'source_ref', 'timeline_eq', 'policy', 'index', 'width', 'height', 'offset')}
    pc['version'] = 1
    body = dict(box=[8, 8, 40, 40], t_ref=1.8, t0=1.799, t1=1.801, seed=pc)
    reset()
    assert fetch(base, url+'/track_object', body) == (200, {'ok': True})
    join()
    status, state = fetch(base, url+'/track_status')
    assert status == 200 and state == dict(state='done', added=1, error=None), state
    assert counts == dict(snapshots=1, timeline_traversals=4, latest_raw_loads=3,
        web_verifications=1, source_current_checks=7, indexed_reads=2,
        person_resolutions=1, vit_initializers=2, committed_notifications=1), counts
    assert len(captures) == 2 and [c.releases for c in captures] == [1, 1]
    assert [c.after_index for c in captures] == [10, 10]
    assert [frame.index for frame in indexed] == [9, 9]
    for frame in indexed:
        np.testing.assert_array_equal(frame.pixels, refs[9])
        assert frame.canonical_s == 1.8 and abs(frame.observed_s-float(pts[9])) < 1e-12
    for frame in initializers:
        np.testing.assert_array_equal(frame, cv2.resize(refs[9], None, fx=.5, fy=.5))
    after = json.loads(path.read_text())
    assert after['detections'][:2] == doc['detections']
    assert after['detections'][-1]['track'] == 18
    assert after['detections'][-1]['aoff'] == [9, -9]
    assert after['detections'][-1]['cbox'] == [-1, 17, 31, 49]
    assert after['audio_redactions'] == doc['audio_redactions']
    assert after['future_top'] == doc['future_top']
    results['strict'] = dict(counts=copy.deepcopy(counts), source_index=9,
        canonical_s=1.8, independent_pts=str(pts[9]), captures=2,
        releases=[c.releases for c in captures], after_indices=[c.after_index for c in captures])
    mode = 'legacy'; reset()
    legacy = dict(box=[8, 8, 40, 40], t_ref=1., t0=.999, t1=1.001)
    assert fetch(base, url+'/track_object', legacy)[0] == 200
    join(); state = fetch(base, url+'/track_status')[1]
    assert state == dict(state='done', added=1, error=None), state
    assert counts == dict(person_resolutions=1, vit_initializers=2,
                          latest_raw_loads=1, committed_notifications=1), counts
    assert len(captures) == 1 and captures[0].releases == 1
    assert 'seed' not in bodies[-1]
    results['legacy'] = dict(counts=copy.deepcopy(counts), body=bodies[-1])
    for label, changed, want in [('null', None, 400),
        ('stale_offset', dict(pc, offset=[999, 999]), 409)]:
        reset(); before = path.read_bytes()
        status, refusal = fetch(base, url+'/track_object', dict(body, seed=changed))
        assert status == want and 'error' in refusal
        assert counts.get('person_resolutions', 0) == 0 and counts.get('committed_notifications', 0) == 0
        assert path.read_bytes() == before and web.FILES.count == 0
        results[label] = dict(status=status, error=refusal, counts=copy.deepcopy(counts))
    assert len(json.loads(path.read_text())['detections']) == 4
    assert web.FILES.count == 0
    results.update(source=str(web.__file__), engine=str(engine.__file__),
        mode=cfg.get('mode', 'source'), media_sha256=fixture['sha256'],
        declared_limit='counts only; no model quality or latency claim')
    (root/'logs/strict-http-counts.json').write_text(json.dumps(results, indent=2)+'\n')
    print('STRICT_AND_LEGACY_LISTENING_HTTP_OK', json.dumps(results), flush=True)
finally:
    server.shutdown(); server_thread.join(8); server.server_close()
    join()
    assert not server_thread.is_alive() and web.FILES.count == 0

# Exercise actual updater copying from the verified built sdist in installed mode.
if cfg.get('mode') == 'installed':
    import openscrub_update as updater
    archives = list(root.glob('dist/*.tar.gz'))
    assert len(archives) == 1, archives
    blob = archives[0].read_bytes()
    destination = root/'updater-fixture'
    destination.mkdir()
    updater.HERE = str(destination)
    updater.urllib.request.urlopen = lambda *args, **kwargs: io.BytesIO(blob)
    updater.update_source(dict(sdist_url='https://fixture.invalid/verified-sdist',
        sha256=hashlib.sha256(blob).hexdigest()), lambda message: None)
    checked = {}
    for name in ('openscrub.py', 'openscrub_web.py', 'openscrub_internal/exact_samples.py',
                 'tests/test_strict_tracker_seed.py', 'tests/test_strict_tracking_routes.py'):
        digest = hashlib.sha256((destination/name).read_bytes()).hexdigest()
        assert digest == cfg['files'][name]
        checked[name] = digest
    (root/'logs/updater-bytes.json').write_text(json.dumps(checked, indent=2)+'\n')
    print('VERIFIED_SDIST_UPDATER_BYTES_OK', json.dumps(checked), flush=True)
