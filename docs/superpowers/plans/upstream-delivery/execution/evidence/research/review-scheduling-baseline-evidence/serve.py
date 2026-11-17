"""Isolated actual-source Flask fixture, with response-boundary ordering gates."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time

ROOT = Path('/tmp/openscrub-review-scheduling-20261117')
ap = argparse.ArgumentParser()
ap.add_argument('--source', default='baseline')
ap.add_argument('--port', type=int, default=18509)
opts = ap.parse_args()
sys.path.insert(0, str(ROOT / opts.source))
os.environ['OPENSCRUB_NO_AUTOFETCH'] = '1'
import openscrub
import openscrub_web as web
import cv2
import numpy as np
from flask import request
from cheroot.wsgi import Server

data = ROOT / ('data-' + opts.source)
data.mkdir(exist_ok=True)
for name in ('JOBS_DIR', 'ZONES_PATH', 'MODEL_SELECT_PATH', 'CERT_DIR',
             'WEB_SETTINGS_PATH', 'CUSTOM_CATS_PATH'):
    setattr(web, name, str(data / Path(getattr(web, name)).name))
Path(web.JOBS_DIR).mkdir(exist_ok=True)
for name in ('CUSTOM_CERT','CUSTOM_KEY','AUTO_CERT','AUTO_KEY'):
    setattr(web,name,str(Path(web.CERT_DIR)/Path(getattr(web,name)).name))
openscrub._model_dir = lambda: str(data / 'models')
openscrub._fetch_model = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('No model downloads in baseline'))
video = data / 'synthetic.avi'
frame = np.indices((180, 320)).sum(axis=0).astype('uint8')
frame = np.stack([frame, 255-frame, frame // 2], axis=-1)
vw = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'MJPG'), 10, (320, 180))
for _ in range(10):
    vw.write(frame)
vw.release()
assert video.stat().st_size > 0
image = data / 'synthetic.jpg'
assert cv2.imwrite(str(image), frame[:80, :120])
manifest = []
fixture_counts = [('small',12),('beta',3),('cold',3)]
if opts.source == 'baseline':
    fixture_counts += [('oneK',1000), ('tenK',10000)]
for jid, count in fixture_counts:
    job = web.new_job(str(video), {}, 'synthetic ' + jid)
    web.JOBS.pop(job['id'])
    job['id'] = jid
    job['phase'] = 'review'
    job['progress'] = 1
    web.JOBS[jid] = job
    rows = []
    for g in range(count):
        n = 1 if g % 2 == 0 else 2
        cat = 'mrn' if g % 2 == 0 else ('face' if g % 4 == 1 else 'person')
        for m in range(n):
            rows.append(openscrub.Detection(.1 + .01*m, .6 + .01*m, (30,30,100,100),
                cat, 'synthetic group ' + str(g), .8 + .1*m, (0,0),
                dense=n>1, track=g if n>1 else -1, person=g if cat=='person' else -1))
    state = {'fps':10., 'cum':[(0,0)]*10, 'bands':[(0,0)]*10,
             'detections':rows, 'input_sha256':hashlib.sha256(video.read_bytes()).hexdigest()}
    report = Path(job['dir'])/'report.json'
    openscrub.write_report(str(report), openscrub.build_parser().parse_args([str(video)]), state)
    doc = json.loads(report.read_text())
    # A saved ordinary mixed track: the highest-confidence representative is enabled.
    if count > 1:
        doc['detections'][1]['enabled'] = False
    report.write_text(json.dumps(doc, indent=1))
    if jid != 'cold':
        for i in range(len(rows)):
            target=Path(job['dir'])/('thumb2_%d.jpg'%i)
            if not target.exists():
                os.link(image,target)
    manifest.append({'job':jid,'groups':count,'rows':len(rows),'report_bytes':report.stat().st_size,
                     'report_sha256':hashlib.sha256(report.read_bytes()).hexdigest(),
                     'mixed_group_members':[1,2] if count>1 else []})
(ROOT/('fixtures-'+opts.source+'.json')).write_text(json.dumps(manifest, indent=2))

# No model/release access is relevant to the review flow.
web.app.view_functions['update_check'] = lambda: web.jsonify({'current':openscrub.VERSION,'update_available':False})
lock=threading.Lock()
events=[]
held=set()
gates={}
counter=0
original_thumb=web.app.view_functions['job_thumb']
def thumb(jid, i):
    global counter
    with lock:
        counter+=1
        token=counter
        gate=threading.Event()
        if jid not in held:
            gate.set()
        gates[token]=gate
        entry={'token':token,'job':jid,'i':i,'entered':time.monotonic(),
               'cache_before':(Path(web.JOBS[jid]['dir'])/('thumb2_%d.jpg'%i)).exists()}
        events.append(entry)
    try:
        response=original_thumb(jid,i)
        with lock:
            entry['production_done']=time.monotonic()
        released=gate.wait(15)  # bounded even if a browser assertion fails
        with lock:
            entry['gate_released']=released
            entry['returned']=time.monotonic()
        return response
    finally:
        with lock:
            gates.pop(token,None)
web.app.view_functions['job_thumb']=thumb

@web.app.route('/__qa__/state')
def qa_state():
    with lock:
        return web.jsonify({'events':list(events),'held':list(held),'pending_tokens':list(gates)})

@web.app.route('/__qa__/control',methods=['POST'])
def qa_control():
    command=request.get_json()
    with lock:
        if 'hold' in command:
            held.update(command['hold'])
        if command.get('release_all'):
            held.clear()
            for gate in gates.values():gate.set()
        for token in command.get('release',[]):
            if token in gates:gates[token].set()
    return web.jsonify({'ok':True})

print(json.dumps({'source':opts.source,'python':sys.version,'cv2':cv2.__version__,
                  'flask':__import__('importlib.metadata').metadata.version('Flask'),
                  'port':opts.port,'fixtures':manifest}),flush=True)
Server(('127.0.0.1',opts.port),web.app,numthreads=24).start()
