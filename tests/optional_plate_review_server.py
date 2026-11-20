"""Local optional-review fixture; saves use real report transactions."""
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys

source, runtime, port = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), int(sys.argv[3])
sys.path.insert(0, str(source))
runtime.mkdir(parents=True, exist_ok=True)
os.environ['OPENSCRUB_NO_AUTOFETCH'] = '1'
os.environ['OPENSCRUB_MEDIA_ROOT'] = str(runtime)
import openscrub_web as web

web._data_root = lambda: str(runtime)
for name in ('JOBS_DIR', 'ZONES_PATH', 'MODEL_SELECT_PATH', 'WEB_SETTINGS_PATH', 'CUSTOM_CATS_PATH'):
    setattr(web, name, str(runtime / Path(getattr(web, name)).name))
Path(web.JOBS_DIR).mkdir(exist_ok=True)
web.JOBS = {}
web.FILES = type(web.FILES)(web.VAULT_LOCK)
web.WORK_Q = queue.Queue()
web.TOKEN = None
web.app.view_functions['update_check'] = lambda: web.jsonify({'current': web.openscrub.VERSION, 'update_available': False})
# This test exercises real saves and reopen; render pixels are tested elsewhere.
web.app.view_functions['job_render'] = lambda jid: web.jsonify(ok=True)
video = runtime / 'source.mp4'
subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error', '-f', 'lavfi',
                '-i', 'color=c=gray:s=160x96:r=5:d=2', '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p', str(video)], check=True)
base = {'category':'plate','text':'plate','cbox':[30,20,100,60],
        'aoff':[0,0], 'last_seen':.2, 'dense':True, 'track':3, 'person':-1, 'poly':[]}
rows = [
    dict(base, t_start=.2, t_end=.25, confidence=.9, enabled=False,
         policy_evidence={'origin':'detection','frame':1,'geometry_valid':True}),
    dict(base, t_start=.4, t_end=.45, confidence=.91, enabled=True,
         policy_evidence={'origin':'detection','frame':2,'geometry_valid':True}),
    dict(base, t_start=.25, t_end=.4, confidence=.8, enabled=False,
         policy_evidence={'origin':'interpolation','frame':None,'geometry_valid':False}),
]
doc = {'plate_policy_evidence_version':1,
       'provenance':{'input':str(video),'input_sha256':hashlib.sha256(video.read_bytes()).hexdigest(),
                     'settings':{'uncertain_policy':'manual_review','plate_threshold':.1,'plate_auto_cutoff':.8}},
       'render_state':{'fps':5,'cum':[[0,0]]*10,'bands':[[0,0]]*10},'detections':rows}
jobs = {}
for label in ('desktop', 'mobile'):
    job = web.new_job(str(video), {}, 'policy-review-' + label + '.mp4')
    job['phase'], job['progress'] = 'review', .5
    Path(job['dir'], 'report.json').write_text(json.dumps(doc))
    jobs[label] = job['id']
(runtime / 'fixture.json').write_text(json.dumps({'jobs':jobs}))
from cheroot.wsgi import Server
server = Server(('127.0.0.1', port), web.app, numthreads=4)
try:
    server.start()
finally:
    server.stop()
