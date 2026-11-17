"""One-off P08/S02 probe against a complete git archive; no proposed cache."""
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import builtins
import hashlib
import json
import os
import sys
import shutil
import threading

SHA = 'e21ebdf6e3ee46e6c65050dc956a9a3459152269'
ROOT = Path('/tmp/openscrub-thumbnail-baseline-20261117')
EXPORT = ROOT / 'export'
sys.path.insert(0, str(EXPORT))
sys.path.insert(1, '/tmp/openscrub-baseline-20261116')
import baseline_isolation
baseline_isolation.ROOT = ROOT
shutil.rmtree(ROOT / 'synthetic-data' / 'route-probe', ignore_errors=True)
web = baseline_isolation.configure('route-probe')
import openscrub
import cv2
import numpy as np
assert Path(web.__file__).parent == EXPORT
assert Path(openscrub.__file__).parent == EXPORT
cv2.setNumThreads(1)
web.app.testing = True
web.JOBS.clear()
DATA = Path(web.JOBS_DIR)
DATA.mkdir(parents=True, exist_ok=True)
jobdir = DATA / 'synthetic'
jobdir.mkdir(exist_ok=True)
report = jobdir / 'report.json'
video = jobdir / 'input.avi'
normalized = jobdir / 'normalized.avi'


def make_video(path, swap=False):
    frame = np.zeros((144, 320, 3), dtype=np.uint8)
    frame[:, :100] = (255, 32, 32) if not swap else (32, 32, 255)
    frame[:, 100:190] = (32, 255, 32) if not swap else (255, 32, 255)
    frame[:, 190:] = (32, 255, 255) if not swap else (255, 255, 32)
    # Visibly nonblank regions; channel differences already exceed std >8.
    frame[::8, :] = frame[::8, :] // 2
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 4, (320, 144))
    assert writer.isOpened()
    for _ in range(4):
        writer.write(frame)
    writer.release()


make_video(video)
make_video(normalized, True)
args = SimpleNamespace(video=str(video))
state = {'fps': 4, 'cum': [(0, 0)] * 4, 'bands': [],
         'detections': [openscrub.Detection(0.0, 0.75, (48, 48, 80, 80),
                                          'manual', 'synthetic', 1.0)
                        for _ in range(4)]}
# Real pinned writer, then real Flask mutation endpoint for geometry.
openscrub.write_report(str(report), args, state)
job = {'id': 'synthetic', 'dir': str(jobdir), 'video': str(video),
       'output': None, 'phase': 'review', 'options': {}, 'log': [],
       'cancel': threading.Event()}
web.JOBS[job['id']] = job
BASE = '/api/jobs/synthetic'
counts = {'report_open_read': 0, 'report_open_write': 0, 'report_json_load': 0,
          'frame_at_calls': 0, 'jpeg_open_read': 0}
lock = threading.Lock()
real_open, real_load, real_frame = builtins.open, json.load, web._frame_at

def inc(name):
    with lock:
        counts[name] += 1


def counted_open(file, mode='r', *a, **kw):
    name = os.fspath(file) if isinstance(file, (str, bytes, os.PathLike)) else ''
    if name == str(report):
        inc('report_open_write' if any(m in mode for m in 'wa+') else 'report_open_read')
    if str(name).endswith('.jpg') and 'r' in mode:
        inc('jpeg_open_read')
    return real_open(file, mode, *a, **kw)


def counted_load(fp, *a, **kw):
    if getattr(fp, 'name', '') == str(report):
        inc('report_json_load')
    return real_load(fp, *a, **kw)


def counted_frame(*a, **kw):
    inc('frame_at_calls')
    return real_frame(*a, **kw)


builtins.open, json.load, web._frame_at = counted_open, counted_load, counted_frame
results = []
artifacts = ROOT / 'images'
artifacts.mkdir(exist_ok=True)


def identity(path):
    st = path.stat()
    return {'path': str(path), 'dev': st.st_dev, 'ino': st.st_ino,
            'size': st.st_size, 'mtime_ns': st.st_mtime_ns, 'ctime_ns': st.st_ctime_ns,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def request(path, method='GET', body=None, headers=None, image_name=None):
    with web.app.test_client() as client:
        response = client.open(BASE + path, method=method, json=body, headers=headers or {})
        data = response.get_data()
        out = {'request': method + ' ' + BASE + path, 'status': response.status_code,
               'headers': {k: v for k, v in response.headers.items()
                           if k.lower() in {'content-type', 'content-length', 'cache-control',
                                            'etag', 'last-modified', 'expires'}},
               'sha256': hashlib.sha256(data).hexdigest()}
        if response.is_json:
            out['body'] = response.get_json()
        if response.mimetype == 'image/jpeg' and data:
            image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            h, w = image.shape[:2]
            out['image'] = {'shape': list(image.shape),
                            'center_bgr_mean': np.round(image[h//2-5:h//2+5,w//2-5:w//2+5].mean(axis=(0, 1)), 2).tolist()}
            if image_name:
                target = artifacts / image_name
                target.write_bytes(data)
                out['image_path'] = str(target)
        response.close()
        return out


def case(name, work):
    before = counts.copy()
    observations = work()
    results.append({'case': name, 'counts': {k: counts[k] - before[k] for k in counts},
                    'report_identity': identity(report), 'source_identity': identity(Path(job['video'])),
                    'responses': observations})


case('cold_one', lambda: [request('/thumb/0', image_name='cold-left.jpg')])
case('warm_three', lambda: [request('/thumb/0') for _ in range(3)])
case('warm_conditional', lambda: [request('/thumb/0', headers={'If-None-Match': results[0]['responses'][0]['headers']['ETag']})])
# All real request handlers. Deliberately synchronized starts, no substituted route/parser.
def parallel(paths):
    barrier = threading.Barrier(len(paths))
    def run(path):
        barrier.wait()
        return request(path)
    with ThreadPoolExecutor(max_workers=len(paths)) as pool:
        return list(pool.map(run, paths))


case('parallel_cold_four', lambda: ([(jobdir / f'thumb2_{i}.jpg').unlink(missing_ok=True) for i in range(4)] and parallel(['/thumb/0','/thumb/1','/thumb/2','/thumb/3'])))
case('parallel_readonly_consumers', lambda: parallel(['/detections', '/boxes_at?t=0', '/detections', '/boxes_at?t=0']))
case('geometry_post_same_row', lambda: [request('/detections', 'POST', {'box_overrides': {'0': [208, 48, 240, 80]}}),
                                      request('/boxes_at?t=0'), request('/thumb/0', image_name='geometry-stale-left.jpg'),
                                      request('/detframe/0', image_name='geometry-current-full.jpg')])
case('geometry_forced_cold_control', lambda: [(jobdir/'thumb2_0.jpg').unlink(), request('/thumb/0', image_name='geometry-current-right.jpg')])
# Atomic same-length replacement with restored mtime: relevant to future publisher integration.
before_replace = identity(report)
doc = json.loads(report.read_text())
doc['detections'][0]['cbox'] = [108.0, 48.0, 140.0, 80.0]
replacement = jobdir / 'report-stage.json'
replacement.write_text(json.dumps(doc, indent=1))
assert replacement.stat().st_size == before_replace['size']
os.utime(replacement, ns=(report.stat().st_atime_ns, before_replace['mtime_ns']))
os.replace(replacement, report)
case('same_size_atomic_report_replace', lambda: [request('/boxes_at?t=0'), request('/thumb/0', image_name='atomic-stale-right.jpg')])
results[-1]['previous_report_identity'] = before_replace
case('atomic_replace_forced_cold_control', lambda: [(jobdir/'thumb2_0.jpg').unlink(), request('/thumb/0', image_name='atomic-current-middle.jpg')])
# Actual mutable source field consumed by pinned production routes; same as normalization selection.
job['video'] = str(normalized)
case('normalized_source_switch', lambda: [request('/frame_at?t=0', image_name='normalized-current-full.jpg'),
                                        request('/thumb/0', image_name='normalized-stale-middle.jpg')])
case('normalized_source_forced_cold_control', lambda: [(jobdir/'thumb2_0.jpg').unlink(), request('/thumb/0', image_name='normalized-current-middle.jpg')])
# A replacement at the same source pathname also changes actual bytes, not only the label.
before_source_replace = identity(normalized)
replacement_source = jobdir/'replacement.avi'
make_video(replacement_source, False)
os.replace(replacement_source, normalized)
case('source_atomic_replace_same_path', lambda: [request('/frame_at?t=0', image_name='replaced-current-full.jpg'),
                                             request('/thumb/0', image_name='replaced-stale-middle.jpg')])
results[-1]['previous_source_identity'] = before_source_replace
case('source_replace_forced_cold_control', lambda: [(jobdir/'thumb2_0.jpg').unlink(), request('/thumb/0', image_name='replaced-current-middle.jpg')])
# Warm path also hides report corruption/removal: expose without changing product code.
saved = report.read_bytes()
report.write_bytes(b'{broken')
case('warm_with_corrupt_report', lambda: [request('/thumb/0')])
report.write_bytes(saved)
builtins.open, json.load, web._frame_at = real_open, real_load, real_frame
output = {'source_sha': SHA, 'modules': {'web': web.__file__, 'engine': openscrub.__file__},
          'opencv': cv2.__version__, 'jobs_dir': web.JOBS_DIR,
          'fixture': '4 MJPEG frames, 320x144 at 4 fps, visibly different colored thirds; four report rows',
          'counts_scope': 'builtins.open for exact report and JPEG; json.load exact report; _frame_at wraps actual pinned function',
          'cases': results}
print(json.dumps(output, indent=2))
