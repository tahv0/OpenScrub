"""Exact guarded source/installed defaults, runtime identities and evaluated JS."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

import openscrub
import openscrub_web as web
import cv2
from openscrub_internal.job_logs import JobLog

root = Path(os.environ['VERIFY_RUN'])
cfg = json.loads(Path(os.environ['VERIFY_CONFIG']).read_text())
mode = cfg.get('mode', 'source')
expected_root = Path(cfg['installed_target'] if mode == 'installed' else cfg['source'])
assert Path(openscrub.__file__).resolve() == expected_root / 'openscrub.py'
assert Path(web.__file__).resolve() == expected_root / 'openscrub_web.py'
assert hashlib.sha256(Path(web.__file__).read_bytes()).hexdigest() == cfg['files']['openscrub_web.py']
defaults = vars(openscrub.build_parser().parse_args(['synthetic.mp4']))
versions = {}
for name in ['opencv-python', 'numpy', 'Flask', 'Pillow', 'cheroot', 'pytest']:
    try:
        versions[name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        versions[name] = None
js = root / 'logs/evaluated-app.js'
js.write_text(web.APP_JS)
node = subprocess.run(['node', '--check', str(js)], capture_output=True, text=True)
assert node.returncode == 0, node.stdout + node.stderr
record = {'mode': mode, 'python': sys.version, 'executable': sys.executable,
          'opencv': cv2.__version__, 'versions': versions, 'defaults': defaults,
          'defaults_count': len(defaults), 'web': web.__file__, 'engine': openscrub.__file__,
          'page_sha256': hashlib.sha256(web.PAGE.encode()).hexdigest(),
          'app_js_sha256': hashlib.sha256(web.APP_JS.encode()).hexdigest(),
          'node_check': node.returncode, 'job_logs': JobLog(['installed boundary']).snapshot()}
if mode == 'installed':
    source = json.loads((Path(__file__).parents[1] / 'source-defaults.json').read_text())
    assert defaults == source['defaults']
    assert record['page_sha256'] == source['page_sha256']
    assert record['app_js_sha256'] == source['app_js_sha256']
    assert len(record['job_logs']['lines']) == 1
(root / ('logs/audit-' + mode + '.json')).write_text(json.dumps(record, indent=2, default=str) + '\n')
print(json.dumps(record, default=str))
