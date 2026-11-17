import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import openscrub_web as web
ROOT = Path('/tmp/openscrub-task4')
assert Path(web.__file__).resolve().parent == Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
runtime = ROOT / 'runtime'
runtime.mkdir(exist_ok=True)
for name in ('JOBS_DIR', 'ZONES_PATH', 'MODEL_SELECT_PATH', 'CERT_DIR',
             'WEB_SETTINGS_PATH', 'CUSTOM_CATS_PATH'):
    setattr(web, name, str(runtime / Path(getattr(web, name)).name))
for name in ('CUSTOM_CERT', 'CUSTOM_KEY', 'AUTO_CERT', 'AUTO_KEY'):
    setattr(web, name, str(Path(web.CERT_DIR) / Path(getattr(web, name)).name))
Path(web.JOBS_DIR).mkdir(exist_ok=True)
job = web.new_job('', {}, 'synthetic-eta-stage.mp4')
job['phase'] = 'scanning'
cb = web.WebCallbacks(job)
clock = SimpleNamespace(now=0)
web.time = SimpleNamespace(monotonic=lambda: clock.now, time=time.time, sleep=time.sleep)
web.app.view_functions['update_check'] = lambda: web.jsonify({'current': web.openscrub.VERSION, 'update_available': False})
@web.app.route('/_qa/observe', methods=['POST'])
def observe():
    payload = web.request.get_json()
    clock.now = payload['t']
    if 'phase' in payload:
        job['phase'] = payload['phase']
    cb.progress(payload['stage'], payload['cur'], payload['total'])
    return web.jsonify(web.job_public(job))
(ROOT/'server-job.json').write_text(json.dumps({'id': job['id']}))
from cheroot.wsgi import Server
print('Task4 synthetic ETA server http://127.0.0.1:18487', flush=True)
Server(('127.0.0.1',18487), web.app, numthreads=4).start()
