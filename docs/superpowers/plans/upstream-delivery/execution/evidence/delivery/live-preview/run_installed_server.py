from pathlib import Path
import json
import os
import runpy
import threading

from task5_isolation import configure
web = configure('installed-http')
root = Path('/tmp/openscrub-task5')
site = root / 'install/lib/python3.12/site-packages'
assert Path(web.__file__).resolve() == site / 'openscrub_web.py'
assert Path(web.openscrub.__file__).resolve() == site / 'openscrub.py'
print('IMPORTS', web.openscrub.__file__, web.__file__, flush=True)
import cv2
import numpy as np
jobdir = Path(web.JOBS_DIR) / 'installed-preview'
jobdir.mkdir(exist_ok=True)
job = dict(id='installed-preview', dir=str(jobdir), name='synthetic preview',
           phase='scanning', progress=0.0, error=None, stats={}, log=[], output=None,
           cancel=threading.Event())
web.JOBS[job['id']] = job
frame = np.random.default_rng(20261117).integers(0,256,(240,720,3),dtype=np.uint8)
web.WebCallbacks(job).scan_frame(frame,0.0,0)
expected = cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,70])[1].tobytes()
assert (jobdir/'preview.jpg').read_bytes() == expected
(root/'installed-expected.jpg').write_bytes(expected)
print('ENTRYPOINT',site/'bin/openscrub-web',flush=True)
runpy.run_path(str(site/'bin/openscrub-web'),run_name='__main__')
