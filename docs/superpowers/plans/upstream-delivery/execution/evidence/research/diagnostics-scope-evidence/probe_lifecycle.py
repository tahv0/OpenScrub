"""Bounded baseline-only full-module probes; no donor execution or HTTP listener."""
import json, os, pathlib, signal, socket, sys, threading
ROOT = pathlib.Path('/tmp/openscrub-diagnostics-scope-20261117')
SOURCE = ROOT / '12919c96c6f7558136b50d7b4d85e5e6b62f1971'
mode = sys.argv[1]
case = ROOT / 'runtime' / ('worker' if mode in ('worker', 'restart') else mode)
case.mkdir(parents=True, exist_ok=True)
sys.dont_write_bytecode = True
sys.path.insert(0, str(SOURCE))
# All network requests fail before connecting, including accidental model fetches.
def no_connect(*args, **kwargs): raise AssertionError('network forbidden in diagnostic research')
socket.socket.connect = no_connect
import openscrub_web as web
import openscrub
assert pathlib.Path(web.__file__).resolve().parent == SOURCE
assert pathlib.Path(openscrub.__file__).resolve().parent == SOURCE
web._HERE = str(case)
web._data_root = lambda: str(case)
for attr, name in [('JOBS_DIR','jobs'),('ZONES_PATH','zones.json'),('MODEL_SELECT_PATH','model_select.json'),('WEB_SETTINGS_PATH','web_settings.json'),('CERT_DIR','certs')]:
    setattr(web, attr, str(case / name))
pathlib.Path(web.JOBS_DIR).mkdir(exist_ok=True)
openscrub.user_data_dir = lambda: str(case / 'config')
openscrub._fetch_model = no_connect

def result(data):
    (case / (mode + '.json')).write_text(json.dumps(data, indent=2) + '\n')

if mode == 'worker':
    job = web.new_job(str(case / 'missing-PATH_SENTINEL_OCR_PLATE_PROVIDER.mp4'), {'categories':'','use_zones':False}, 'NAME_SENTINEL')
    # Uploaded input survives even when the selected source fails.
    (pathlib.Path(job['dir']) / 'input.mp4').write_bytes(b'inert synthetic placeholder')
    web.WebCallbacks(job).log('OCR_SENTINEL query=PLATE_SENTINEL provider=PROVIDER_SENTINEL')
    web.enqueue(job, 'scan')
    worker = web.start_worker()
    web.WORK_Q.join()
    # Cursor is an absolute list index; no retention trim occurs.
    for n in range(1205): web.WebCallbacks(job).log('synthetic line %d' % n)
    response = web.app.test_client().get('/api/jobs/%s/log?from=1200' % job['id'])
    before = {'id':job['id'], 'phase':job['phase'], 'error':job['error'], 'log_len':len(job['log']), 'sentinel_in_log': any('OCR_SENTINEL' in str(v) for v in job['log']), 'status_log_len':web.job_public(job)['log_len'], 'status_tail_len':len(web.job_public(job)['log_tail']), 'cursor_payload':response.get_json(), 'worker_alive_after_job_error':worker.is_alive()}
    # Exercise the existing watchdog through a stopped real worker.
    web.WORK_Q.put(None); worker.join(2)
    assert not worker.is_alive()
    restarted = web.check_worker()
    worker2 = web.WORKER['thread']
    web.WORK_Q.put(None); worker2.join(2)
    before['watchdog_restarted_worker'] = restarted
    before['owners_after_stop'] = web.FILES.count
    before['job_files'] = sorted(p.name for p in pathlib.Path(job['dir']).iterdir())
    result(before)
elif mode == 'restart':
    web.rehydrate_jobs()
    recovered = list(web.JOBS.values())
    assert len(recovered) == 1
    job = recovered[0]
    result({'id':job['id'], 'phase':job['phase'], 'error':job['error'], 'log':job['log'], 'files':sorted(p.name for p in pathlib.Path(job['dir']).iterdir()), 'diagnostics_files':list(str(p.relative_to(case)) for p in case.rglob('*') if p.is_file() and ('log' in p.name or 'running' in p.name))})
elif mode in ('startup_failure','sigterm'):
    sys.argv = ['openscrub-web', '--http', '--retain-days', '0', '--host', '127.0.0.1', '--token', 'TOKEN_SENTINEL']
    def serve(*args):
        result({'source':web.__file__, 'jobs_dir':web.JOBS_DIR, 'listener_opened':False, 'worker_alive':web.WORKER['thread'].is_alive(), 'diagnostic_files_before_exit':list(str(p.relative_to(case)) for p in case.rglob('*') if p.is_file())})
        if mode == 'sigterm': os.kill(os.getpid(), signal.SIGTERM)
        raise RuntimeError('SERVE_EXCEPTION_SENTINEL')
    web._serve = serve
    web.main()
else:
    raise AssertionError(mode)
