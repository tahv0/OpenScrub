"""Local no-worker fixture for the real Scan Setup page and job intake."""
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
video = runtime / 'source.mp4'
subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error', '-f', 'lavfi',
                '-i', 'color=c=gray:s=160x96:r=5:d=2', '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p', str(video)], check=True)
(runtime / 'fixture.json').write_text(json.dumps({'video': str(video), 'jobs': web.JOBS_DIR}))
from cheroot.wsgi import Server
server = Server(('127.0.0.1', port), web.app, numthreads=4)
try:
    server.start()
finally:
    server.stop()
