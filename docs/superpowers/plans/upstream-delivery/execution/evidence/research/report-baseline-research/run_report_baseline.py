#!/usr/bin/env python3
"""Pinned full-module Flask/socket baseline; synthetic data only. See README.md.

Export the pinned Git archive and source the existing env-opencv4.sh first.
No application source is edited. Large files remain under --work-dir.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager

BASE = '5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f'
PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument('--source', type=Path, required=True)
PARSER.add_argument('--work-dir', type=Path, required=True)
PARSER.add_argument('--output', type=Path, required=True)
PARSER.add_argument('--rows', nargs='+', type=int, default=[1000,10000,100000])
ARGS = PARSER.parse_args()
ARGS.source = ARGS.source.resolve()
ARGS.work_dir.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ARGS.source))
import openscrub as engine
import openscrub_web as web
import cv2
from werkzeug.serving import make_server

# All mutable paths use task-local synthetic storage. No startup worker is run.
web._data_root = lambda: str(ARGS.work_dir)
for name in ('JOBS_DIR', 'ZONES_PATH', 'MODEL_SELECT_PATH', 'CERT_DIR',
             'WEB_SETTINGS_PATH', 'CUSTOM_CATS_PATH'):
    setattr(web, name, str(ARGS.work_dir / Path(getattr(web, name)).name))
web.TOKEN = None
web.app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)
jobdir = ARGS.work_dir / 'jobs' / 'synthetic'
jobdir.mkdir(parents=True, exist_ok=True)
report_path = jobdir / 'report.json'
web.JOBS.clear()
web.JOBS['synthetic'] = {'dir': str(jobdir), 'video': str(jobdir / 'input.avi'),
                         'log': [], 'state': 'review'}
engine._model_dir = lambda: os.environ['OPENSCRUB_BASELINE_MODEL_DIR']
def forbidden_fetch(*a, **kw):
    raise RuntimeError('Research policy: no model fetching')
engine._fetch_model = forbidden_fetch


def rss_bytes():
    with open('/proc/self/status') as f:
        for line in f:
            if line.startswith('VmRSS:'):
                return int(line.split()[1]) * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixture(rows):
    fps = 30
    frames = max(1800, rows * 3)
    cum = [[round((i % 240) * 0.1, 1), round((i % 300) * 0.2, 1)]
           for i in range(frames)]
    detections = []
    for i in range(rows):
        t = (i * 3) / fps
        cat = ('name', 'plate', 'face', 'manual', 'person')[i % 5]
        detections.append(dict(t_start=t, t_end=t + 0.15,
            cbox=[10, 12, 44, 36], category=cat,
            text='synthetic-%06d' % i, confidence=0.85, aoff=cum[min(i*3, frames-1)],
            last_seen=t + .1, enabled=(i % 11 != 0), dense=(i % 5 >= 2),
            track=i // 5 if i % 5 >= 2 else -1,
            person=i // 25 if cat == 'face' else -1,
            poly=[[[10.,12.],[44.,12.],[44.,36.],[10.,36.]]] if cat == 'person' else []))
    # Preserve a real ordinary allowlist suggestion case as well as group fields.
    for i in (0, 5):
        if i < rows:
            detections[i].update(category='name', text='synthetic-recurring', enabled=False)
    return dict(provenance={'tool':'openscrub', 'version':engine.VERSION,
        'input':str(jobdir/'input.avi'), 'input_sha256':None,
        'settings':{'categories':'name,plate,face,person'}},
        render_state={'fps':fps, 'cum':cum,
                      'bands':[[round((i%17)*.2,1),round((i%19)*.2,1)] for i in range(frames)]},
        detections=detections,
        audio_redactions=[{'t0':.2,'t1':.4,'mode':'mute'}, {'t0':.5,'t1':.7,'mode':'bleep'}],
        audio_suggestions=[{'t0':.1,'t1':.3,'text':'synthetic audio','category':'name'}],
        audio_transcript=[{'start':0.,'end':1.,'text':'synthetic audio'}])


def reset(doc):
    report_path.write_text(json.dumps(doc, indent=1), encoding='utf-8')


def read():
    return json.loads(report_path.read_text())


class JsonProbe:
    def __init__(self, failure=None):
        self.failure = failure
        self.counts = {'parses':0,'serializations':0,'report_write_opens':0,
                       'stream_write_calls':0,'output_characters':0}
    def __getattr__(self, name):
        return getattr(json, name)
    def load(self, f, *a, **kw):
        if Path(f.name).resolve() == report_path.resolve():
            self.counts['parses'] += 1
        return json.load(f, *a, **kw)
    def dump(self, doc, f, *a, **kw):
        self.counts['serializations'] += 1
        self.counts['report_write_opens'] += 1  # dump receives the real open file
        if self.failure == 'encoding':
            raise TypeError('injected encoder failure after destination opened')
        if self.failure == 'write':
            f.write('{"detections": [')
            raise OSError('injected interrupted write after 16 characters')
        probe = self
        class Sink:
            def write(self, s):
                probe.counts['stream_write_calls'] += 1
                probe.counts['output_characters'] += len(s)
                return f.write(s)
        return json.dump(doc, Sink(), *a, **kw)


@contextmanager
def instrument(failure=None):
    old = web.json
    probe = JsonProbe(failure)
    web.json = probe
    try:
        yield probe
    finally:
        web.json = old


server = make_server('127.0.0.1', 0, web.app, threaded=True)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
url = 'http://127.0.0.1:%d/api/jobs/synthetic/detections' % server.server_port

def post(payload, transport='socket'):
    raw = json.dumps(payload, separators=(',',':')).encode()
    if transport == 'test-client':
        with web.app.test_client() as client:
            response = client.post('/api/jobs/synthetic/detections', data=raw,
                                   content_type='application/json')
            return response.status_code, response.get_json(silent=True), len(raw)
    req = urllib.request.Request(url, data=raw, headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            return response.status, json.loads(response.read()), len(raw)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors='replace'), len(raw)


def preservation(original, actual, changed_indices=()):
    expected = copy.deepcopy(original)
    for i in changed_indices:
        expected['detections'][i]['enabled'] = actual['detections'][i]['enabled']
    return {'all_other_fields_equal': expected == actual,
            'rows': len(actual['detections']),
            'audio_redactions_equal': original['audio_redactions'] == actual.get('audio_redactions'),
            'audio_suggestions_equal': original['audio_suggestions'] == actual.get('audio_suggestions'),
            'audio_transcript_equal': original['audio_transcript'] == actual.get('audio_transcript'),
            'render_state_equal': original['render_state'] == actual.get('render_state')}


def regressions():
    result = {}
    doc = fixture(10)
    for transport in ('test-client','socket'):
        for failure in ('encoding','write'):
            reset(doc)
            old = report_path.read_bytes()
            with instrument(failure) as probe:
                status, body, size = post({'enabled':{'1':False}}, transport)
            new = report_path.read_bytes()
            try:
                read(); valid = True
            except json.JSONDecodeError:
                valid = False
            result[transport+'-'+failure] = {'status':status, 'payload_bytes':size,
                'before_bytes':len(old), 'after_bytes':len(new),
                'previous_bytes_preserved':old == new, 'valid_json_after_failure':valid,
                'counts':probe.counts}
    reset(doc)
    payload = {'manual':[{'t_start':.2,'t_end':.8,'t_ref':.3,'screen_box':[10,12,44,36]}]}
    old = report_path.read_bytes()
    first = post(payload)
    # The first response is deliberately ignored by the caller; replay bytes are identical.
    after_first = read()
    second = post(payload)
    after_second = read()
    result['socket-identical-manual-replay'] = {
        'statuses':[first[0],second[0]], 'request_bytes':first[2],
        'row_counts':[len(doc['detections']),len(after_first['detections']),len(after_second['detections'])],
        'duplicate_added_rows_equal':after_second['detections'][-1] == after_second['detections'][-2],
        'existing_rows_preserved':after_second['detections'][:len(doc['detections'])] == doc['detections'],
        'other_fields_preserved':all(after_second[k] == doc[k] for k in doc if k != 'detections')}
    reset(doc)
    original_load = web._load_job_report
    barrier = threading.Barrier(2, timeout=10)
    first_done = threading.Event()
    responses = {}
    errors = []
    def controlled_load(job):
        snapshot = original_load(job)
        from flask import request
        index = int(next(iter(request.get_json()['enabled'])))
        barrier.wait()
        if index == 2 and not first_done.wait(10):
            raise RuntimeError('first request did not finish')
        return snapshot
    web._load_job_report = controlled_load
    def save(index):
        try:
            responses[index] = post({'enabled':{str(index):False}})
        except Exception as exc:
            errors.append(repr(exc))
        finally:
            if index == 1: first_done.set()
    try:
        threads = [threading.Thread(target=save,args=(i,)) for i in (1,2)]
        for t in threads: t.start()
        for t in threads: t.join(20)
        if any(t.is_alive() for t in threads): raise RuntimeError('overlap thread stuck')
    finally:
        web._load_job_report = original_load
    actual = read()
    result['socket-overlapping-sparse-saves'] = {
        'schedule':'Both real threaded socket requests read old report; request disabling row 1 completes; request disabling row 2 writes stale snapshot.',
        'statuses':{str(k):v[0] for k,v in responses.items()}, 'errors':errors,
        'expected_enabled':[False,False],
        'actual_enabled':[actual['detections'][i]['enabled'] for i in (1,2)],
        'other_field_preservation':preservation(doc,actual,(1,2))}
    reset(doc)
    with instrument() as probe:
        status, body, size = post({'enabled':{'1':False},
            'box_overrides':{'2':[12,14,46,38]},'time_overrides':{'3':[.2,.7]},
            'audio':[{'t0':.1,'t1':.5,'mode':'bleep'}]})
    actual = read()
    result['socket-ordinary-combined-edit'] = {'status':status,'response':body,
        'counts':probe.counts, 'rows':len(actual['detections']),
        'enabled_applied':actual['detections'][1]['enabled'] is False,
        'box_applied':actual['detections'][2]['cbox'] == [12.,14.,46.,38.],
        'time_applied':[actual['detections'][3]['t_start'],actual['detections'][3]['t_end']] == [.2,.7],
        'audio_applied':actual['audio_redactions'] == [{'t0':.1,'t1':.5,'mode':'bleep'}],
        'suggest_allowlist_preserved':body.get('suggest_allowlist') == ['synthetic-recurring']}
    return result


def measure(rows):
    doc = fixture(rows)
    reset(doc)
    initial_bytes = report_path.stat().st_size
    frame_count = len(doc['render_state']['cum'])
    info = {'rows':rows, 'initial_report_bytes':initial_bytes,
        'fps':30,'frame_count':frame_count,'duration_seconds':frame_count/30,
        'motion_history_pairs':frame_count,
        'motion_history_json_bytes':len(json.dumps(doc['render_state']['cum'],separators=(',',':')).encode()),
        'band_history_pairs':len(doc['render_state']['bands']),
        'dense_rows':sum(d['dense'] for d in doc['detections']),
        'manual_rows':sum(d['category']=='manual' for d in doc['detections']),
        'distinct_tracks':len({d['track'] for d in doc['detections'] if d['track']>=0}),
        'disabled_rows':sum(not d['enabled'] for d in doc['detections']),
        'payload_bytes':{'sparse':len(json.dumps({'enabled':{'1':False}},separators=(',',':')).encode()),
                         'no_op':len(b'{"enabled":{}}'),
                         'bulk':len(json.dumps({'enabled':{str(i):False for i in range(rows)}},separators=(',',':')).encode())},
        'cache_state':'Application has no report cache. Three warm-up route operations per scenario; filesystem cache remains OS managed and is not dropped.',
        'scenarios':{}}
    del doc
    for scenario in ('sparse','no_op'):
        # Sparse toggles a single choice on each request; no-op submits an empty map.
        samples=[]
        initial_rss = rss_bytes()
        peak = [initial_rss]
        stop = threading.Event()
        def sample_rss():
            while not stop.wait(.01): peak[0] = max(peak[0],rss_bytes())
        sampler=threading.Thread(target=sample_rss,daemon=True)
        sampler.start()
        before = report_path.read_bytes()
        for iteration in range(8):
            payload = {'enabled':{'1':bool(iteration % 2)}} if scenario=='sparse' else {'enabled':{}}
            with instrument() as probe:
                start=time.perf_counter()
                status,body,request_bytes=post(payload)
                elapsed=time.perf_counter()-start
            if status != 200: raise RuntimeError('unexpected HTTP status '+str(status))
            sample={'seconds':elapsed,'status':status,'counts':probe.counts.copy(),'payload_bytes':request_bytes}
            if iteration>=3: samples.append(sample)
        stop.set(); sampler.join(2)
        after = report_path.read_bytes()
        info['scenarios'][scenario]={'warmups':3,'measured_repetitions':5,'samples':samples,
            'median_seconds':statistics.median(s['seconds'] for s in samples),
            'rss_before_bytes':initial_rss,'sampled_peak_rss_bytes':peak[0],
            'process_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            'report_bytes':len(after),'identical_report_bytes':before==after,
            'after_sha256':digest(after)}
        print(json.dumps({'progress_rows':rows,'scenario':scenario,
                         'median_seconds':info['scenarios'][scenario]['median_seconds']}),flush=True)
        del before,after
    actual = read()
    original = fixture(rows)
    info['preservation']=preservation(original,actual,(1,))
    report_path.unlink()
    return info


def render_preservation():
    import numpy as np
    video=jobdir/'input.avi'
    writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),30,(160,96))
    if not writer.isOpened(): raise RuntimeError('synthetic AVI writer unavailable')
    for i in range(60):
        frame=np.full((96,160,3), 50+i*2,dtype=np.uint8)
        cv2.putText(frame,str(i),(70,50),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,0),1)
        writer.write(frame)
    writer.release()
    doc=fixture(10)
    doc['render_state']['cum']=[[0.,0.] for _ in range(60)]
    doc['render_state']['bands']=[[0.,0.] for _ in range(60)]
    doc['provenance']['input_sha256']=engine.sha256_file(str(video))
    doc['detections'][4].update(enabled=False,zone_dropped=True)
    # Identity includes ordinary index, label, dense track and person fields.
    reset(doc)
    loaded,rstate,prov=engine.load_report(str(report_path))
    result={'before_rows':len(doc['detections']),
        'before_enabled_rows':sum(d['enabled'] for d in doc['detections']),
        'before_disabled_texts':[d['text'] for d in doc['detections'] if not d['enabled']],
        'load_report_rows':len(loaded),
        'loaded_track_person':[[d.text,d.track,d.person] for d in loaded]}
    args=engine.build_parser().parse_args([str(video),'--from-report',str(report_path),
        '--report',str(report_path),'--output',str(jobdir/'rendered.mp4'),'--encoder','x264'])
    start=time.perf_counter()
    try:
        summary=engine.run_pipeline(args)
        result['render_summary']=summary
        result['actual_render_completed']=True
    except Exception as exc:
        result['actual_render_completed']=False
        result['error']=repr(exc)
    result['seconds']=time.perf_counter()-start
    after=read()
    cap=cv2.VideoCapture(str(jobdir/'rendered.mp4'))
    result['output_frames']=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); cap.release()
    result['after_rows']=len(after['detections'])
    result['after_texts']=[d['text'] for d in after['detections']]
    result['after_row_indices_by_original_text']={d['text']:i for i,d in enumerate(after['detections'])}
    result['disabled_rows_lost']=[d['text'] for d in doc['detections'] if not d['enabled'] and d['text'] not in result['after_texts']]
    result['enabled_track_person_preserved']=all(
        (d.text,d.track,d.person) in [(r['text'],r.get('track',-1),r.get('person',-1)) for r in after['detections']]
        for d in loaded)
    for field in ('audio_redactions','audio_suggestions','audio_transcript'):
        result[field]={'present_before':field in doc,'present_after':field in after,
            'equal':doc.get(field)==after.get(field)}
    (ARGS.work_dir/'render-before.json').write_text(json.dumps(doc,indent=2))
    (ARGS.work_dir/'render-after.json').write_text(json.dumps(after,indent=2))
    result['render_before_artifact']=str(ARGS.work_dir/'render-before.json')
    result['render_after_artifact']=str(ARGS.work_dir/'render-after.json')
    result['video_bytes']=video.stat().st_size
    result['output_bytes']=(jobdir/'rendered.mp4').stat().st_size if (jobdir/'rendered.mp4').exists() else 0
    return result


evidence={'upstream_sha':BASE,'date':'2026-11-16',
    'source_snapshot':str(ARGS.source),
    'source_sha256':{name:digest((ARGS.source/name).read_bytes()) for name in ('openscrub.py','openscrub_web.py')},
    'python':sys.version,'platform':platform.platform(),'opencv':cv2.__version__,
    'cpu':platform.processor(),'logical_cpus':os.cpu_count(),
    'scope':'Unmodified full baseline imports; real Flask routes with test-client and loopback threaded Werkzeug HTTP; no browser, no TLS, no production deployment.',
    'fixture_seed':'deterministic formulas; no RNG',
    'limits':['Single host Linux/Python 3.12/OpenCV4','No filesystem-cache drops','Socket client and server share process; RSS includes fixture/client/instrumentation',
        'JSON stream proxy adds per-write Python accounting overhead; timings are instrumented baseline only',
        'No model inference or real footage; synthetic motion/groups/audio; no performance speedup claim',
        'Overlap schedule explicitly controlled at report load; not an estimate of random race frequency']}
try:
    evidence['regressions']=regressions()
    evidence['render_preservation']=render_preservation()
    evidence['measurements']=[measure(n) for n in ARGS.rows]
finally:
    server.shutdown(); thread.join(3); server.server_close()
    ARGS.output.parent.mkdir(parents=True,exist_ok=True)
    ARGS.output.write_text(json.dumps(evidence,indent=2))
print('Evidence: '+str(ARGS.output),flush=True)
