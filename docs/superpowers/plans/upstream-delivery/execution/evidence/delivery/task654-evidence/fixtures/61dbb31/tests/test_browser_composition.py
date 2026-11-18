"""Combined editor/review ownership at actual retaining/removal boundaries."""
from test_review_save_failures import run_js


def test_retaining_panel_keeps_editor_owner_and_gesture():
    run_js("""setup();
    const cv=document.createElement('canvas');elements.set('beCv',cv);
    const slot=elements.get('beslot');slot.contains=node=>node===cv;
    let disconnected=0;
    BE.drag={kind:'move'};const gesture=BE.drag;
    BE_VIEW={cv,editor:BE,observer:{disconnect(){disconnected++}}};
    const owner=BE_VIEW;
    showPanel('boxedit_rev');
    assert.equal(BE_VIEW,owner);assert.equal(BE.drag,gesture);assert.equal(disconnected,0);
    """)


def test_successful_render_removal_releases_editor_owner():
    run_js("""setup();
    const cv=document.createElement('canvas');elements.set('beCv',cv);
    const review=elements.get('review');review.contains=node=>node===cv;
    let disconnected=0;
    BE.drag={kind:'move'};
    BE_VIEW={cv,editor:BE,observer:{disconnect(){disconnected++}}};
    const p=saveAndRender();await reply();await reply();await p;
    assert.equal(BE_VIEW,null);assert.equal(BE.drag,null);assert.equal(disconnected,1);
    """)


# Reuse the production PAGE/routes with the same loopback HTTP/body-gate pattern
# as test_job_polling_browser. Media is tiny and synthetic; only unrelated update
# metadata and explicit failure/ACK/body gates are controlled.
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest


@pytest.fixture
def combined_http(monkeypatch, tmp_path):
    import cv2
    import numpy as np
    import openscrub as engine
    import openscrub_web as web

    monkeypatch.setattr(web, 'JOBS', {})
    monkeypatch.setattr(web, 'JOBS_DIR', str(tmp_path / 'jobs'))
    Path(web.JOBS_DIR).mkdir()
    video = tmp_path / 'tiny.mp4'
    raw = tmp_path / 'tiny-raw.mp4'
    writer = cv2.VideoWriter(str(raw), cv2.VideoWriter_fourcc(*'mp4v'), 10, (320, 180))
    assert writer.isOpened()
    frame = np.full((180, 320, 3), 200, np.uint8)
    frame[30:75, 40:110] = (30, 170, 230)
    for _ in range(30):
        writer.write(frame)
    writer.release()
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error', '-i', str(raw),
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], check=True)
    names = {'A': 'Family &amp; friends — café.mp4', 'B': 'Other synthetic.mp4',
             'default': 'Default SDR.mp4'}
    initial = {}
    for jid in names:
        options = {} if jid == 'default' else {'mode': 'box', 'pad': 0, 'encoder': 'x264'}
        job = web.new_job(str(video), options, names[jid])
        web.JOBS.pop(job['id'])
        job.update(id=jid, phase='review', progress=1.)
        web.JOBS[jid] = job
        web.WebCallbacks(job).log('log-' + jid)
        count = 1 if jid == 'default' else 102
        rows = [engine.Detection(0., 2.9, (40, 30, 110, 75), 'email', 'synthetic ' + str(i),
                                 .9, (0, 0), track=0 if i < 2 else -1)
                for i in range(count)]
        state = {'fps': 10., 'cum': [(0, 0)] * 30, 'bands': [(0, 0)] * 30,
                 'detections': rows}
        args = engine.build_parser().parse_args([str(video)])
        report = Path(job['dir']) / 'report.json'
        engine.write_report(str(report), args, state)
        doc = json.loads(report.read_text())
        doc['unknown_task654'] = {'kept': True}
        doc['audio_redactions'] = [{'t0': .5, 't1': .7, 'mode': 'mute'}]
        if jid != 'default':
            doc['detections'][-1].update(zone_dropped=True, enabled=False)
        report.write_text(json.dumps(doc))
        initial[jid] = doc
    monkeypatch.setitem(web.app.view_functions, 'update_check',
                        lambda: web.jsonify({'current': engine.VERSION, 'update_available': False}))
    # Render dispatch invokes the actual worker synchronously. Its processing,
    # report/raw/source/FILES path is unchanged; no permanent worker is created.
    monkeypatch.setattr(web, 'enqueue', lambda job, action: web._run_job(job, action))
    state = {'hold_log': False, 'hold_thumb': False, 'hold_ack': False, 'fail_save': False,
             'log_entered': 0, 'thumb_entered': 0, 'ack_entered': 0}
    log_gate, thumb_gate, ack_gate = (threading.Event() for _ in range(3))
    for gate in (log_gate, thumb_gate, ack_gate):
        gate.set()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            if self.path == '/__qa__/control':
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                for key, gate in [('hold_log', log_gate), ('hold_thumb', thumb_gate), ('hold_ack', ack_gate)]:
                    if key in data:
                        state[key] = data[key]
                        gate.clear() if data[key] else gate.set()
                if 'fail_save' in data:
                    state['fail_save'] = data['fail_save']
                if 'append' in data:
                    web.WebCallbacks(web.JOBS['A']).log(data['append'])
                return self.send_payload(200, json.dumps(state).encode())
            self.forward()

        def do_GET(self):
            if self.path == '/__qa__/state':
                return self.send_payload(200, json.dumps(state).encode())
            self.forward()

        def send_payload(self, status, body, content_type='application/json', gate=None):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                if gate is not None and body:
                    self.wfile.write(body[:1]);self.wfile.flush()
                    assert gate.wait(20), 'bounded controlled HTTP body/ACK gate expired'
                    body = body[1:]
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # obsolete browser transport cancelled after headers

        def forward(self):
            path = urlsplit(self.path).path
            save = self.command == 'POST' and path.endswith('/detections')
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            if save and state['fail_save']:
                return self.send_payload(423, b'{"error":"controlled save refusal"}')
            with web.app.test_client() as client:
                result = client.open(self.path, method=self.command, data=body,
                                     content_type=self.headers.get('Content-Type'))
                payload = result.get_data()
                content_type, status = result.content_type, result.status_code
                result.close()
            gate = None
            if path == '/api/jobs/A/log' and state['hold_log']:
                state['log_entered'] += 1;gate = log_gate
            elif '/thumb/' in path and state['hold_thumb']:
                state['thumb_entered'] += 1;gate = thumb_gate
            elif save and state['hold_ack'] and status == 200:
                state['ack_entered'] += 1;gate = ack_gate
            self.send_payload(status, payload, content_type, gate)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(server.server_port), web, initial
    finally:
        for gate in (log_gate, thumb_gate, ack_gate):
            gate.set()
        server.shutdown();server.server_close();thread.join(timeout=3)


def test_combined_real_page_owner_interactions(combined_http):
    node = shutil.which('node')
    if not node or not os.environ.get('OPENSCRUB_PLAYWRIGHT_MODULE'):
        pytest.skip('Existing prepared Playwright required; no install')
    base, web, initial = combined_http
    env = dict(os.environ, COMBINED_BASE=base)
    result = subprocess.run([node, str(Path(__file__).with_suffix('.cjs'))], env=env,
                            capture_output=True, text=True, timeout=120)
    artifacts = Path(os.environ['VERIFY_RUN']) / 'logs'
    (artifacts / 'combined-browser.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    saved = json.loads(Path(web.JOBS['A']['dir'], 'report.json').read_text())
    assert len(saved['detections']) == len(initial['A']['detections'])
    assert saved['unknown_task654'] == initial['A']['unknown_task654']
    assert saved['audio_redactions'] == [{'t0': 1, 't1': 1.2, 'mode': 'bleep'}]
    for before, after in zip(initial['A']['detections'], saved['detections']):
        for key, value in before.items():
            if key != 'enabled':
                assert after[key] == value, key


def test_tiny_actual_default_sdr_control(combined_http):
    import cv2
    base, web, initial = combined_http
    with web.app.test_client() as client:
        result = client.post('/api/jobs/default/render')
        assert result.status_code == 200, result.get_json()
        job = web.JOBS['default']
        assert job['phase'] == 'done', job.get('error')
        capture = cv2.VideoCapture(job['output'])
        try:
            ok, frame = capture.read()
        finally:
            capture.release()
        assert ok and frame.shape == (180, 320, 3)
        doc = json.loads(Path(job['dir'], 'report.json').read_text())
        assert doc['unknown_task654'] == initial['default']['unknown_task654']
        assert len(doc['detections']) == 1
        assert doc['audio_redactions'] == initial['default']['audio_redactions']
