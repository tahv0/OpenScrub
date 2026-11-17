import importlib.util
import json
import sys
from pathlib import Path

SOURCE = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
ROOT = Path('/tmp/openscrub-task620')
sys.path.insert(0, str(SOURCE))
import baseline_isolation
baseline_isolation.ROOT = ROOT
web = baseline_isolation.configure('browser-runtime')
web.TOKEN = None
spec = importlib.util.spec_from_file_location('roundtrip_tests', SOURCE / 'tests/test_report_roundtrip.py')
tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
job = web.new_job('', {'categories': 'email', 'engine': 'tesseract', 'device': 'cpu',
    'encoder': 'x264', 'mode': 'box', 'no_ner': True, 'no_memory': True, 'pad': 0},
    'synthetic-task620.avi')
fixture = tests.review.__wrapped__(Path(job['dir']))
job['video'] = str(fixture.video)
job['phase'] = 'review'
(ROOT / 'render-before.json').write_text(json.dumps(fixture.doc, indent=2))
(ROOT / 'job.json').write_text(json.dumps({'id': job['id'], 'dir': job['dir'],
    'video': job['video'], 'source': str(SOURCE)}))
web.app.view_functions['update_check'] = lambda: web.jsonify({'current': web.openscrub.VERSION, 'update_available': False})
web.start_worker()
from cheroot.wsgi import Server
print('Task620 synthetic review http://127.0.0.1:18488', flush=True)
Server(('127.0.0.1', 18488), web.app, numthreads=8).start()
