"""Bounded P05 research against full pinned exports; no product implementation.

Run with env-opencv4.sh sourced, cwd=ROOT/export, output folder as argv[1].
Only I/O observers/scheduling wrappers, runtime path isolation, and server
lifecycle observation are installed. Actual callback, route, WSGI stack run.
"""
from pathlib import Path
import builtins
import hashlib
import importlib.metadata
import inspect
import json
import os
import platform
import socket
import sys
import threading
import traceback

SHA = 'e21ebdf6e3ee46e6c65050dc956a9a3459152269'
ROOT = Path('/tmp/openscrub-live-preview-baseline-20261117')
EXPORT = ROOT / 'export'
OUT = Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
os.environ['OPENSCRUB_BASELINE_MODEL_DIR'] = str(ROOT / 'synthetic-data/models')
os.environ['OPENSCRUB_NO_AUTOFETCH'] = '1'
sys.path.insert(0, str(EXPORT))
sys.path.insert(1, '/tmp/openscrub-baseline-20261116')
import baseline_isolation
baseline_isolation.ROOT = ROOT
web = baseline_isolation.configure('http-live-preview')
import openscrub
import cv2
import numpy as np
import cheroot.wsgi
import werkzeug.utils
import werkzeug.wsgi

assert Path(web.__file__).parent == EXPORT
assert Path(openscrub.__file__).parent == EXPORT
cv2.setNumThreads(1)
web.JOBS.clear()
jobdir = Path(web.JOBS_DIR) / 'synthetic-preview'
jobdir.mkdir(parents=True, exist_ok=True)
preview = jobdir / 'preview.jpg'
job = {'id': 'synthetic-preview', 'dir': str(jobdir), 'phase': 'scan',
       'cancel': threading.Event(), 'log': []}
web.JOBS[job['id']] = job

# Model helper is blocked by baseline_isolation, and all socket connects
# below are restricted to loopback (no dependency/model/network downloads).
real_connect = socket.socket.connect
def local_connect(self, address):
    if not isinstance(address, tuple) or address[0] not in ('127.0.0.1', '::1'):
        raise RuntimeError('Research permits only loopback socket connects')
    return real_connect(self, address)
socket.socket.connect = local_connect

rng = np.random.default_rng(20261117)
frames = {
    'A-noise': rng.integers(0, 256, (240, 720, 3), dtype=np.uint8),
    'B-red': np.full((240, 720, 3), (24, 24, 224), dtype=np.uint8),
    'C-green-texture': rng.integers(0, 256, (240, 720, 3), dtype=np.uint8),
}
frames['C-green-texture'][:, :300] = (24, 224, 24)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def publish(name, target=job):
    # Fresh callback satisfies the unchanged real 0.4s gate without sleeps.
    cb = web.WebCallbacks(target)
    cb.scan_frame(frames[name], 0.0, 0)
    return (Path(target['dir']) / 'preview.jpg').read_bytes()

expected = {}
for name in frames:
    data = publish(name)
    expected[name] = data
    (OUT / f'expected-{name}.jpg').write_bytes(data)

assert len(expected['A-noise']) > len(expected['C-green-texture']) > 8192
assert len(expected['B-red']) < 8192

def image_info(data):
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) if data else None
    result = {'bytes': len(data), 'sha256': digest(data),
              'matches': [name for name, value in expected.items() if data == value],
              'starts_soi': data.startswith(b'\xff\xd8'),
              'ends_eoi': data.endswith(b'\xff\xd9'), 'decodes': img is not None}
    if img is not None:
        result['shape'] = list(img.shape)
        result['mean_bgr'] = np.round(img.mean(axis=(0, 1)), 3).tolist()
        result['decoded_pixel_mae'] = {
            name: round(float(np.abs(img.astype(float) - cv2.imdecode(
                np.frombuffer(value, np.uint8), cv2.IMREAD_COLOR).astype(float)).mean()), 3)
            for name, value in expected.items()}
    return result

def identity():
    st = preview.stat()
    data = preview.read_bytes()
    return {'inode': st.st_ino, 'size': st.st_size, 'sha256': digest(data)}

state_lock = threading.Lock()
active = None
real_open, real_stat = builtins.open, os.stat
real_start_response = cheroot.wsgi.Gateway.start_response
tls = threading.local()

def observed_start_response(self, status, headers, exc_info=None):
    result = real_start_response(self, status, headers, exc_info)
    tls.response = {'status': status, 'headers': dict(headers),
                    'wsgi_file_wrapper': str(self.env.get('wsgi.file_wrapper')),
                    'socket_headers_already_sent': self.req.sent_headers}
    return result

def pause(schedule, point, **details):
    schedule['events'].append({'event': point, **details})
    schedule['reached'].set()
    if not schedule['resume'].wait(10):
        raise TimeoutError(f'Unreleased schedule at {point}')
    schedule['events'].append({'event': 'resume', 'point': point})

class ObservedFile:
    def __init__(self, fp, schedule):
        self.fp, self.schedule, self.reads = fp, schedule, 0
    def __getattr__(self, name):
        return getattr(self.fp, name)
    def __enter__(self):
        self.fp.__enter__()
        return self
    def __exit__(self, *args):
        return self.fp.__exit__(*args)
    def read(self, *args, **kwargs):
        self.reads += 1
        s = self.schedule
        if s['kind'] == f'read-{self.reads}':
            pause(s, f'before-underlying-read-{self.reads}',
                  requested_args=list(args), offset=self.fp.tell(),
                  open_descriptor_size=os.fstat(self.fp.fileno()).st_size,
                  response=getattr(tls, 'response', None),
                  stack=traceback.format_list(traceback.extract_stack(limit=9)))
        data = self.fp.read(*args, **kwargs)
        s['events'].append({'event': 'actual-file-read', 'read': self.reads,
                            'bytes': len(data), 'sha256': digest(data)})
        return data

def observed_open(file, mode='r', *args, **kwargs):
    fp = real_open(file, mode, *args, **kwargs)
    s = active
    if s is not None and os.fspath(file) == str(preview) and mode == 'rb':
        s['events'].append({'event': 'response-open',
                            'inode': os.fstat(fp.fileno()).st_ino,
                            'size': os.fstat(fp.fileno()).st_size})
        return ObservedFile(fp, s)
    return fp

def observed_stat(path, *args, **kwargs):
    st = real_stat(path, *args, **kwargs)
    s = active
    caller = inspect.currentframe().f_back
    if (s is not None and s['kind'] == 'stat-open-atomic' and
            os.fspath(path) == str(preview) and
            caller.f_code.co_name == 'send_file' and
            caller.f_code.co_filename == werkzeug.utils.__file__):
        pause(s, 'after-actual-send-file-stat-before-return',
              captured_size=st.st_size, captured_inode=st.st_ino)
    return st

builtins.open, os.stat = observed_open, observed_stat
cheroot.wsgi.Gateway.start_response = observed_start_response

server_ready = threading.Event()
server_holder = {}
server_errors = []
real_prepare = cheroot.wsgi.Server.prepare
def observed_prepare(self):
    real_prepare(self)
    server_holder['server'] = self
    server_ready.set()
cheroot.wsgi.Server.prepare = observed_prepare

def serve():
    try:
        web._serve('127.0.0.1', 0, None)
    except BaseException:
        server_errors.append(traceback.format_exc())
        server_ready.set()

server_thread = threading.Thread(target=serve, name='actual-web-serve', daemon=True)
server_thread.start()
assert server_ready.wait(10), 'Actual _serve did not prepare'
assert not server_errors, server_errors
server = server_holder['server']
port = server.socket.getsockname()[1]

def fetch(name):
    raw = bytearray()
    with socket.create_connection(('127.0.0.1', port), timeout=10) as conn:
        conn.sendall((f'GET /api/jobs/{job["id"]}/preview.jpg?case={name} HTTP/1.1\r\n'
                      'Host: 127.0.0.1\r\nConnection: close\r\n\r\n').encode())
        while chunk := conn.recv(65536):
            raw.extend(chunk)
    raw = bytes(raw)
    head, body = raw.split(b'\r\n\r\n', 1)
    header_lines = head.decode('latin1').split('\r\n')
    headers = dict(line.split(': ', 1) for line in header_lines[1:])
    (OUT / f'{name}.http').write_bytes(raw)
    (OUT / f'{name}.body.jpg').write_bytes(body)
    return {'name': name, 'status': header_lines[0], 'headers': headers,
            'body': image_info(body),
            'length_matches': int(headers['Content-Length']) == len(body),
            'raw_http_artifact': f'{name}.http', 'body_artifact': f'{name}.body.jpg'}

cases = []
try:
    for name in ('A-noise', 'B-red', 'C-green-texture'):
        publish(name)
        cases.append(fetch(f'control-{name}'))

    for kind, newer in (('read-1', 'B-red'), ('read-2', 'C-green-texture'),
                         ('stat-open-atomic', 'B-red')):
        publish('A-noise')
        before = identity()
        s = {'kind': kind, 'reached': threading.Event(),
             'resume': threading.Event(), 'events': []}
        active = s
        result_holder, errors = {}, []
        def client():
            try:
                result_holder['response'] = fetch(kind)
            except BaseException:
                errors.append(traceback.format_exc())
        thread = threading.Thread(target=client, name=f'client-{kind}', daemon=True)
        thread.start()
        try:
            assert s['reached'].wait(10), f'Schedule not reached: {kind}; {errors}'
            if kind == 'stat-open-atomic':
                # Synthetic control ONLY: actual producer writes another task-local
                # job's JPEG, then harness atomically replaces served pathname.
                # This does not install a proposed publication helper.
                staged = jobdir / 'atomic-control'
                staged.mkdir(exist_ok=True)
                publish(newer, {'dir': str(staged)})
                os.replace(staged / 'preview.jpg', preview)
                publication = 'actual callback to staging job + harness os.replace'
            else:
                publish(newer)
                publication = 'actual WebCallbacks.scan_frame in-place publication'
            # Path.read_bytes uses io.open, avoiding the response-open observer.
            after = identity()
            s['events'].append({'event': 'publication-completed',
                                'method': publication, 'current': after})
        finally:
            s['resume'].set()
        thread.join(12)
        assert not thread.is_alive(), f'Client remained running: {kind}'
        assert not errors, errors
        active = None
        result = result_holder['response']
        result.update({'before': before, 'after': after, 'new_image': newer,
                       'events': s['events']})
        body = (OUT / result['body_artifact']).read_bytes()
        if kind == 'read-2':
            result['splice_matches_A_first_8192_plus_C_remainder'] = (
                body == expected['A-noise'][:8192] + expected[newer][8192:])
        cases.append(result)
finally:
    if active is not None:
        active['resume'].set()
    active = None
    server.stop()
    server_thread.join(10)
    builtins.open, os.stat = real_open, real_stat
    cheroot.wsgi.Gateway.start_response = real_start_response
    cheroot.wsgi.Server.prepare = real_prepare
    socket.socket.connect = real_connect

# Direct actual-callback throttle control; no sleeps, fake clock or writes.
cb = web.WebCallbacks(job)
cb.scan_frame(frames['A-noise'], 0, 0)
throttle_before = preview.read_bytes()
last_frame_before = cb._last_frame
cb.scan_frame(frames['B-red'], 1, 1)
throttle = {'immediate_second_call_keeps_prior_jpeg': preview.read_bytes() == throttle_before,
            'last_frame_unchanged': cb._last_frame == last_frame_before}

metadata = {
    'base_commit': SHA, 'base_tree': '795af785b672d397d2e287b5b963c10dcc4dbdf8',
    'export': str(EXPORT), 'jobs_dir': web.JOBS_DIR, 'python': sys.version,
    'platform': platform.platform(), 'opencv': cv2.__version__, 'numpy': np.__version__,
    'packages': {p: importlib.metadata.version(p) for p in ('Flask', 'Werkzeug', 'cheroot')},
    'source_sha256': {str(p.relative_to(EXPORT)): digest(p.read_bytes())
                      for p in (EXPORT/'openscrub.py', EXPORT/'openscrub_web.py', EXPORT/'zones_ui.py')},
    'server': {'entrypoint': 'actual openscrub_web._serve(127.0.0.1, 0, None)',
               'type': type(server).__module__ + '.' + type(server).__name__,
               'numthreads': server.requests.min, 'port': port,
               'stopped': not server_thread.is_alive(), 'errors': server_errors},
    'expected': {name: image_info(data) for name, data in expected.items()},
    'throttle_control': throttle, 'cases': cases,
}
(OUT / 'results.json').write_text(json.dumps(metadata, indent=2) + '\n')
for case in cases:
    print(json.dumps({k: case[k] for k in ('name', 'status', 'length_matches', 'body')}))
print(json.dumps({'stopped': metadata['server']['stopped'], 'throttle': throttle}))
assert metadata['server']['stopped'] and not server_errors
assert all(c['length_matches'] and len(c['body']['matches']) == 1 for c in cases[:3])
assert not cases[3]['length_matches'] and cases[3]['body']['matches'] == ['B-red']
assert not cases[4]['length_matches'] and cases[4]['splice_matches_A_first_8192_plus_C_remainder']
assert not cases[5]['length_matches'] and cases[5]['body']['matches'] == ['B-red']
