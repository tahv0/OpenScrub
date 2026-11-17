"""Assert installed identity before actual generated CLI/web entrypoint."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
source=Path(os.environ['TASK1202_SOURCE']).resolve()
import openscrub
import openscrub_web as web
import openscrub_internal.job_logs as logs
for module in (openscrub,web,logs):
    path=Path(module.__file__).resolve()
    assert path.is_relative_to(source),(path,source)
    relative=path.relative_to(source)
    assert path.read_bytes()==(Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')/relative).read_bytes(),relative
    print('INSTALLED_SOURCE',module.__name__,path,hashlib.sha256(path.read_bytes()).hexdigest(),flush=True)
assert not any('/.codex/worktrees/' in p for p in sys.path),sys.path
profile=Path(os.path.expanduser('~')).resolve()
assert Path(web.JOBS_DIR).resolve().is_relative_to(profile)
assert Path(openscrub._model_dir()).resolve().is_relative_to(profile)
print('INSTALLED_DEFAULTS',web.JOBS_DIR,openscrub._model_dir(),flush=True)
kind=sys.argv[1]
if kind=='web':
    Path(web.JOBS_DIR).mkdir(parents=True,exist_ok=True)
    job=web.new_job('',{},'installed synthetic')
    for i in range(2100):
        web.WebCallbacks(job).log('installed-'+str(i))
    print('INSTALLED_JOB',job['id'],flush=True)
    sys.argv=['openscrub-web']+sys.argv[2:]
    runpy.run_path(str(source/'bin/openscrub-web'),run_name='__main__')
else:
    sys.argv=['openscrub','--help']
    runpy.run_path(str(source/'bin/openscrub'),run_name='__main__')
