#!/usr/bin/env python3
"""Actual pinned Flask intake, isolated synthetic media; never start a worker."""
import hashlib
import importlib.metadata
import io
import json
import logging
import os
from pathlib import Path
import platform
import shutil
import socket
import sys
import tempfile
import threading
import traceback

ROOT = Path('/tmp/openscrub-options-input-20261117')
SOURCE = ROOT / 'source'
RUNTIME = ROOT / 'runtime'
EVIDENCE = Path(__file__).resolve().parent
PIN = 'e21ebdf6e3ee46e6c65050dc956a9a3459152269'
assert SOURCE.is_dir() and not RUNTIME.exists(), 'Fresh task runtime required'
RUNTIME.mkdir()
(RUNTIME / 'form-temp').mkdir()
tempfile.tempdir = str(RUNTIME / 'form-temp')
os.environ['OPENSCRUB_NO_AUTOFETCH'] = '1'
os.environ['OPENSCRUB_MEDIA_ROOT'] = str(RUNTIME)
os.environ['OPENSCRUB_MAX_UPLOAD_GB'] = '8'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
original_expanduser = os.path.expanduser
os.path.expanduser = lambda p: str(RUNTIME / 'profile') + str(p)[1:] if str(p).startswith('~') else original_expanduser(p)
sys.path.insert(0, str(SOURCE))

# Reject unexpected networking, inference, worker execution or model fetching.
def forbidden_network(*args, **kwargs):
    raise AssertionError('Research forbids network connections')
socket.socket.connect = forbidden_network
forbidden_calls = []
def profile(frame, event, arg):
    if event == 'call' and frame.f_code.co_filename in (str(SOURCE/'openscrub.py'), str(SOURCE/'openscrub_web.py')):
        if frame.f_code.co_name in {'worker', '_run_job', 'start_worker', 'run_scan', 'run_pipeline', '_fetch_model'}:
            forbidden_calls.append(frame.f_code.co_name)
            raise AssertionError('Forbidden execution: ' + frame.f_code.co_name)
sys.setprofile(profile)
import cv2
import numpy as np
import openscrub as core
import openscrub_web as web
from flask import got_request_exception
assert Path(core.__file__).resolve() == SOURCE/'openscrub.py'
assert Path(web.__file__).resolve() == SOURCE/'openscrub_web.py'
web._data_root = lambda: str(RUNTIME)
for key in ('JOBS_DIR', 'ZONES_PATH', 'MODEL_SELECT_PATH', 'CERT_DIR', 'WEB_SETTINGS_PATH', 'CUSTOM_CATS_PATH'):
    setattr(web, key, str(RUNTIME / Path(getattr(web, key)).name))
for key in ('CUSTOM_CERT', 'CUSTOM_KEY', 'AUTO_CERT', 'AUTO_KEY'):
    setattr(web, key, str(Path(web.CERT_DIR) / Path(getattr(web, key)).name))
Path(web.JOBS_DIR).mkdir()
cv2.setNumThreads(1)
before_threads = [t.name for t in threading.enumerate()]

video = RUNTIME/'synthetic.avi'
writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'MJPG'), 2.0, (64, 48))
assert writer.isOpened()
for i in range(2):
    frame = np.full((48,64,3), 40 + i*60, np.uint8)
    cv2.rectangle(frame, (8,8), (32,30), (200,180,30), -1)
    writer.write(frame)
writer.release()
capture = cv2.VideoCapture(str(video))
decoded = []
while True:
    ok, frame = capture.read()
    if not ok: break
    decoded.append({'shape': list(frame.shape), 'sha256': hashlib.sha256(frame.tobytes()).hexdigest()})
capture.release()
assert len(decoded) == 2
video_bytes = video.read_bytes()
fixture = {'recipe': 'OpenCV MJPG AVI, 64x48, 2 fps, two constant BGR frames (40,100), filled rectangle (8,8)-(32,30) BGR (200,180,30)', 'path':str(video), 'bytes':len(video_bytes), 'sha256': hashlib.sha256(video_bytes).hexdigest(), 'decoded_frames':decoded}

error_log = io.StringIO()
handler = logging.StreamHandler(error_log)
web.app.logger.addHandler(handler)
exceptions = []
def observe_exception(sender, exception, **extra):
    exceptions.append({'type':type(exception).__name__, 'message':str(exception), 'traceback':''.join(traceback.format_exception(exception))})
got_request_exception.connect(observe_exception, web.app, weak=False)
# Normal production error conversion: TESTING and PROPAGATE_EXCEPTIONS remain defaults.
assert not web.app.testing and web.app.config['PROPAGATE_EXCEPTIONS'] is None
client = web.app.test_client()
supported = {'categories':'email', 'mode':'box', 'sample_interval':0.75, 'pad':3, 'no_ner':True, 'use_zones':False}
cases = [
    ('missing', None), ('empty', ''), ('whitespace', '   '),
    ('malformed-object', '{'), ('malformed-token', 'not-json'),
    ('array-empty', '[]'), ('array-nonempty', '[1]'), ('null', 'null'),
    ('string', '"ordinary"'), ('string-empty', '""'),
    ('integer', '7'), ('zero', '0'), ('decimal', '1.5'),
    ('boolean-true', 'true'), ('boolean-false', 'false'),
    ('object-empty', '{}'), ('object-supported', json.dumps(supported)),
    ('object-unknown-key', json.dumps(dict(supported, ordinary_unknown_key={'value':7}))),
]
def files_under(path):
    return [{'path':str(p.relative_to(path)), 'bytes':p.stat().st_size, 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(path.rglob('*')) if p.is_file()]
def queue_items():
    with web.WORK_Q.mutex:
        return [list(x) for x in web.WORK_Q.queue]
results = []
for intake in ('upload', 'server-path'):
    for label, value in cases:
        assert not web.JOBS and web.WORK_Q.empty() and not list(Path(web.JOBS_DIR).iterdir())
        exceptions.clear()
        error_log.seek(0); error_log.truncate()
        data = {}
        if value is not None: data['options'] = value
        if intake == 'upload': data['video'] = (io.BytesIO(video_bytes), 'synthetic.avi')
        else: data['server_path'] = str(video)
        response = client.post('/api/jobs', data=data, content_type='multipart/form-data')
        result = {'intake':intake, 'case':label, 'options_field':value, 'options_present':value is not None,
                  'request_content_type':'multipart/form-data', 'status':response.status_code, 'content_type':response.content_type,
                  'body':response.get_data(as_text=True), 'json':response.get_json(silent=True), 'exceptions':list(exceptions),
                  'job_ids':list(web.JOBS), 'queue':queue_items(), 'job_store_files':files_under(Path(web.JOBS_DIR)),
                  'job_store_directories':[p.name for p in Path(web.JOBS_DIR).iterdir() if p.is_dir()],
                  'form_temp_files':files_under(RUNTIME/'form-temp'), 'jobs':[]}
        for jid, job in list(web.JOBS.items()):
            options_file = Path(job['dir'])/web.OPTIONS_FILE
            j = {'id':jid, 'phase':job['phase'], 'name':job['name'], 'options':job['options'], 'options_type':type(job['options']).__name__,
                 'persisted_options_text':options_file.read_text(), 'video':job['video'], 'size':job['size'], 'qgen':job['qgen'],
                 'input_is_fixture':Path(job['video']).read_bytes()==video_bytes, 'input_owned_by_job':Path(job['video']).parent==Path(job['dir'])}
            before = files_under(Path(job['dir']))
            try:
                args = web.build_args(job)
                j['argument_preparation'] = {'success':True, 'selected':{k:getattr(args,k) for k in ('engine','device','mode','categories','sample_interval','pad','no_ner')}}
            except Exception as error:
                j['argument_preparation'] = {'success':False,'exception_type':type(error).__name__, 'message':str(error), 'traceback':''.join(traceback.format_exception(error))}
            j['argument_preparation_files_unchanged'] = before == files_under(Path(job['dir']))
            j['phase_after_direct_argument_preparation'] = job['phase']
            result['jobs'].append(j)
        result['list_jobs'] = client.get('/api/jobs').get_json()
        # Actual ordinary cancel/delete succeeds without interpreting malformed options.
        cleanup = []
        for jid in list(web.JOBS):
            cancel = client.post(f'/api/jobs/{jid}/cancel')
            cancelled_phase = web.JOBS[jid]['phase']
            qgen = web.JOBS[jid]['qgen']
            deletion = client.delete(f'/api/jobs/{jid}')
            cleanup.append({'id':jid, 'cancel_status':cancel.status_code,'cancel_body':cancel.get_json(), 'cancelled_phase':cancelled_phase,'qgen_after_cancel':qgen,
                            'delete_status':deletion.status_code,'delete_body':deletion.get_json()})
        stale_queue = queue_items()
        drained = []
        while not web.WORK_Q.empty():
            drained.append(list(web.WORK_Q.get_nowait())); web.WORK_Q.task_done()
        result['cleanup'] = {'routes':cleanup, 'stale_queue_after_delete':stale_queue, 'harness_drained_queue':drained,
                             'remaining_job_ids':list(web.JOBS),'remaining_job_store_entries':[p.name for p in Path(web.JOBS_DIR).iterdir()],
                             'queue_size':web.WORK_Q.qsize(),'queue_unfinished_tasks':web.WORK_Q.unfinished_tasks,'server_fixture_unchanged':video.read_bytes()==video_bytes}
        assert not web.JOBS and web.WORK_Q.empty() and not list(Path(web.JOBS_DIR).iterdir())
        assert all(x['cancel_status']==200 and x['delete_status']==200 for x in cleanup)
        if label in ('empty','whitespace','malformed-object','malformed-token'):
            assert response.status_code==500 and not result['job_ids'] and not result['queue'] and not result['job_store_files']
        else:
            assert response.status_code==200 and len(result['jobs'])==1
            assert result['jobs'][0]['options'] == ({} if value is None else json.loads(value))
        results.append(result)
        print(intake, label, response.status_code, 'jobs',len(result['jobs']), 'argument-preparation',result['jobs'][0]['argument_preparation']['success'] if result['jobs'] else 'not reached')

source_files = {str(p.relative_to(SOURCE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(SOURCE.rglob('*')) if p.is_file()}
assert len(source_files)==113, 'Import must not add files to pinned source'
output = {'pin':PIN, 'tree':'795af785b672d397d2e287b5b963c10dcc4dbdf8', 'source':str(SOURCE),
          'imports':{'core':core.__file__,'web':web.__file__}, 'archive_sha256':hashlib.sha256((ROOT/'pinned.tar').read_bytes()).hexdigest(),
          'source_files_sha256':source_files, 'fixture':fixture, 'environment':{'python':sys.version,'executable':sys.executable,'platform':platform.platform(),
          'packages':{k:importlib.metadata.version(k) for k in ('opencv-python','numpy','Flask','Werkzeug')}, 'testing':web.app.testing,
          'propagate_exceptions':web.app.config['PROPAGATE_EXCEPTIONS'], 'token':web.TOKEN, 'media_root':os.environ['OPENSCRUB_MEDIA_ROOT']},
          'cases':results,'forbidden_calls':forbidden_calls,'threads_before':before_threads,'threads_after':[t.name for t in threading.enumerate()]}
assert not forbidden_calls and output['threads_before']==output['threads_after']
shutil.rmtree(RUNTIME)
output['final_cleanup'] = {'runtime_removed':not RUNTIME.exists(),'source_retained':SOURCE.exists(),'archive_retained':(ROOT/'pinned.tar').exists()}
(EVIDENCE/'results.json').write_text(json.dumps(output,indent=2)+'\n')
sys.setprofile(None)
print('Recorded',len(results),'route cases; runtime removed:',not RUNTIME.exists())
