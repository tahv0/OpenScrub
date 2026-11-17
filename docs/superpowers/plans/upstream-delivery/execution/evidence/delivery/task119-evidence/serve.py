import hashlib
import json
import os
from pathlib import Path
import sys
from task119_isolation import configure
print('PROCESS', json.dumps({'pid':os.getpid(),'cwd':str(Path.cwd()),'task_root':'/tmp/openscrub-task119','sitecustomize':sys.modules['sitecustomize'].__file__}),flush=True)
web = configure('browser-' + os.environ.get('TASK119_VARIANT', 'native'))
expected = Path(os.environ.get('TASK119_SOURCE', '/home/tahv0/.codex/worktrees/c832/OpenScrub'))
for module in (web.openscrub, web):
    path = Path(module.__file__).resolve()
    assert path == expected / (module.__name__ + '.py'), path
    print('SOURCE', path, hashlib.sha256(path.read_bytes()).hexdigest(), flush=True)
# Actual intake/list/detail/download routes; only the worker phase/output is
# controlled, so display QA does not scan/render or fetch optional models.
def phase_fixture(job, mode):
    assert mode == 'scan'
    output = Path(job['dir']) / 'result.mkv'
    output.write_bytes(b'synthetic output for literal-name QA')
    (output.parent / 'report.json').write_text('{"synthetic":true}')
    job.update(phase='done', progress=1.0, output=str(output))
web.enqueue = phase_fixture
web.app.view_functions['update_check'] = lambda: web.jsonify({
    'current': web.openscrub.VERSION, 'update_available': False})
media=Path('/tmp/openscrub-task119/runtime/media')
media.mkdir(exist_ok=True)
name="Friends' \"summer\" & snow ☃ — &quot;.mp4"
(media/name).write_bytes(b'synthetic server input')
os.environ['OPENSCRUB_MEDIA_ROOT']=str(media)
print('SERVER_INPUT', str(media/name), flush=True)
from cheroot.wsgi import Server
Server(('127.0.0.1',18489),web.app,numthreads=4).start()
