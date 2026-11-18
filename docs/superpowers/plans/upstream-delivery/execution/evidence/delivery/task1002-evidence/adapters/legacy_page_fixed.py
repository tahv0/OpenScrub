"""One full shipped PAGE legacy Track failure/draft smoke; explicit model double."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from werkzeug.serving import make_server
import openscrub as engine
import openscrub_web as web

root = Path(os.environ['VERIFY_RUN'])
out = root/'browser'
out.mkdir()
manifest = json.loads(Path(os.environ['OPENSCRUB_EXACT_MEDIA']).read_text())
source = Path(manifest['cfr5']['path'])
assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest['cfr5']['sha256']
web.TOKEN = None
web.UPD['cache'] = (time.time(), None)  # keep the update-notice fixture offline
job = web.new_job('', {}, 'Legacy Track compatibility')
video = Path(job['dir'])/'input.mp4'
shutil.copyfile(source, video)
job.update(video=str(video), phase='review')
path = Path(job['dir'])/'report.json'
row = dict(t_start=0., t_end=2., last_seen=.5, cbox=[20, 30, 50, 60],
    aoff=[0, 0], category='manual', text='synthetic retained row', confidence=1., enabled=True)
doc = dict(provenance=dict(input=str(video), settings={}),
    render_state=dict(fps=5, cum=[[0, 0]]*10, bands=[[0, 0]]*10),
    detections=[row, dict(row, enabled=False, text='disabled row')],
    audio_redactions=[], future={'keep': True})
path.write_text(json.dumps(doc))
before = path.read_bytes()
entered, release = threading.Event(), threading.Event()
threads, bodies, polls, errors = [], [], [], []
engine.PersonDetector = lambda *args, **kwargs: None
def compute(*args, **kwargs):
    assert 'strict_seed' not in kwargs
    entered.set()
    assert release.wait(10), 'ordinary UI did not poll the real status route'
    error = RuntimeError('deterministic legacy tracking failure')
    errors.append(error)
    raise error
engine.track_manual_region = compute
real_start = web._start_owned_thread
def start(target, lease):
    thread = real_start(target, lease)
    threads.append(thread)
    return thread
web._start_owned_thread = start
@web.app.before_request
def capture_body():
    if web.request.path.endswith('/track_object'):
        bodies.append(web.request.get_json())
@web.app.after_request
def release_after_running_poll(response):
    if web.request.path.endswith('/track_status') and response.is_json:
        state = response.get_json()
        polls.append(state)
        if state['state'] == 'running':
            release.set()
    return response
server = make_server('127.0.0.1', 0, web.app, threaded=True)
thread = threading.Thread(target=server.serve_forever)
thread.start()
try:
    script = Path(__file__).with_suffix('.cjs')
    child = subprocess.run(['/usr/bin/node', str(script),
        'http://127.0.0.1:'+str(server.server_port), job['id'], str(out)],
        capture_output=True, text=True, timeout=40)
    (root/'logs/legacy-page.stdout').write_text(child.stdout)
    (root/'logs/legacy-page.stderr').write_text(child.stderr)
    assert child.returncode == 0, (child.returncode, child.stdout, child.stderr)
    assert entered.is_set() and len(bodies) == 1 and 'seed' not in bodies[0]
    assert set(bodies[0]) == {'box', 't_ref', 't0', 't1'}
    assert any(p['state'] == 'running' for p in polls)
    assert polls[-1] == dict(state='done', added=0, error='deterministic legacy tracking failure')
    assert path.read_bytes() == before and len(errors) == 1
    result = dict(page_sha256=hashlib.sha256(web.PAGE.encode()).hexdigest(),
        browser='Browser plugin not available; prepared Playwright1.65.1/Chromium1255',
        payload=bodies[0], polls=polls, report_unchanged=True,
        doubles=['PersonDetector unavailable', 'tracker raises after first real running status poll',
                 'offline update-notice cache', 'pre-existing pending drafts seeded into existing editor owner'],
        limits='desktop legacy protocol only; no exact UI migration/resize/quality claim')
    (root/'logs/legacy-page-results.json').write_text(json.dumps(result, indent=2)+'\n')
    print('FULL_SHIPPED_PAGE_LEGACY_TRACK_OK', json.dumps(result), flush=True)
finally:
    release.set()
    server.shutdown(); thread.join(8); server.server_close()
    for worker in threads:
        worker.join(8); assert not worker.is_alive()
    assert not thread.is_alive() and web.FILES.count == 0
