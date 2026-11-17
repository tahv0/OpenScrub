import atexit
import json
import os
from pathlib import Path
import sys

from task108_isolation import configure
web = configure(os.environ['TASK108_SERVER_NAME'])
expected = Path(os.environ['TASK108_IMPORT_ROOT']).resolve()
assert Path(web.__file__).resolve() == expected/'openscrub_web.py'
assert Path(web.openscrub.__file__).resolve() == expected/'openscrub.py'
print('IMPORTS', web.openscrub.__file__, web.__file__, flush=True)
# Preserve main() and _serve(): suppress only worker execution and watchdog
# restarts so an admitted control remains queued without model inference.
web.start_worker = lambda: None
web._worker_watchdog = lambda: None

def forbidden(*a, **k):
    raise AssertionError('Task108 HTTP smoke forbids worker/inference/model fetching')
for name in ('worker', '_run_job'):
    setattr(web, name, forbidden)
for name in ('run_pipeline', '_fetch_model'):
    setattr(web.openscrub, name, forbidden)

@web.app.after_request
def record_admission(response):
    from flask import request
    if request.path.startswith('/api/jobs'):
        with web.WORK_Q.mutex:
            queued = list(web.WORK_Q.queue)
        print('ADMISSION', json.dumps({'method':request.method, 'path':request.path,
              'status':response.status_code, 'jobs':list(web.JOBS), 'queue':queued,
              'files':[str(p.relative_to(web.JOBS_DIR)) for p in Path(web.JOBS_DIR).rglob('*')]}), flush=True)
    return response

@atexit.register
def final_state():
    while not web.WORK_Q.empty():
        web.WORK_Q.get_nowait()
        web.WORK_Q.task_done()
    print('FINAL', json.dumps({'jobs':list(web.JOBS), 'queue':web.WORK_Q.qsize(),
          'unfinished':web.WORK_Q.unfinished_tasks}), flush=True)

entrypoint = os.environ.get("TASK108_ENTRYPOINT")
if entrypoint:
    import runpy
    print("ENTRYPOINT", entrypoint, flush=True)
    runpy.run_path(entrypoint, run_name="__main__")
else:
    web.main()
