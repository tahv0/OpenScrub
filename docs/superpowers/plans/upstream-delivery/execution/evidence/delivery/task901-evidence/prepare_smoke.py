"""Caller-owned immutable product export/config; no product execution."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
ROOT = Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task901')
REPO = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
HEAD = 'f44e0b786ad065010fbfd2b8328350bde44116ec'
BASE = '4670641cb8e53e6daa6f77fb505397bfdb6733b8'
source = ROOT / 'product-export'
source.mkdir()
blob = subprocess.check_output(['git', '-C', str(REPO), 'archive', HEAD])
with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
    archive.extractall(source)
files = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source.rglob('*')) if p.is_file()}
assert files['openscrub_web.py'] == '04af11cce1eaf4be0dc157ba5b4d78783a85bcbbb17596078c75d9df79f46c93'
(source / '.verification-source.json').write_text(json.dumps({'head': HEAD, 'base': BASE}) + '\n')
# Export and runs are siblings; owned run guards cannot modify the export.
runs = ROOT / 'product-runs'
runs.mkdir()
required = ['openscrub.py', 'openscrub_web.py', 'zones_ui.py', 'openscrub_internal/__init__.py', 'openscrub_internal/job_logs.py', 'tests/test_job_logs.py', 'tests/test_job_polling_node.py', 'tests/test_job_polling_browser.py', 'tests/test_browser_log_retention.py', 'tests/test_browser_log_benchmark.py', 'test_openscrub.py', 'pyproject.toml', 'README.md', 'benchmark/browser_logs.py', 'benchmark/browser_logs.js', 'benchmark/browser_logs_env.py', 'benchmark/browser_logs_summary.py', 'benchmark/README.md']
modules = {'openscrub': 'openscrub.py', 'openscrub_web': 'openscrub_web.py', 'zones_ui': 'zones_ui.py', 'openscrub_internal': 'openscrub_internal/__init__.py', 'openscrub_internal.job_logs': 'openscrub_internal/job_logs.py', 'openscrub_update': 'openscrub_update.py'}
backend = '/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1203/build-tools'
bootstrap = '/tmp/openscrub-baseline-20261116/bootstrap/lib/python3.14/site-packages'
prerequisites = []
for name in (backend + '/hatchling/__init__.py', bootstrap + '/pip/__init__.py', '/tmp/openscrub-baseline-20261116/synthetic-data/models-opencv4/face_detection_yunet_2023mar.onnx'):
    prerequisites.append({'path': name, 'sha256': hashlib.sha256(Path(name).read_bytes()).hexdigest()})
config = {'task': 'task901', 'scratch': str(runs), 'source': str(source), 'source_kind': 'export', 'policy': 'frozen', 'head': HEAD, 'base': BASE, 'files': files, 'modules': modules,
          'python': '/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python', 'python_version': [3, 12, 16], 'min_free_bytes': 2_000_000_000,
          'configure_app': True, 'prerequisites': prerequisites, 'excluded_paths': [str(REPO), '/home/tahv0/src/OpenScrub'],
          'environment': {'LD_LIBRARY_PATH': '/tmp/openscrub-baseline-20261116/tools/usr/lib/x86_64-linux-gnu:/tmp/openscrub-baseline-20261116/tools/usr/lib/x86_64-linux-gnu/pulseaudio', 'TESSDATA_PREFIX': '/tmp/openscrub-baseline-20261116/tools/usr/share/tesseract-ocr/5/tessdata'},
          'package': {'tool_paths': [backend, bootstrap], 'sdist_files': required, 'wheel_files': list(modules.values()), 'requires_python': '>=3.9', 'installed_commands': [
              ['{target}/bin/openscrub', '--help'],
              [str(Path(__file__).parent / 'listening_smoke.py'), '{target}']]}}
(ROOT / 'product312.json').write_text(json.dumps(config, indent=2) + '\n')
config.update(python='/tmp/openscrub-python39-20261117/venv/bin/python', python_version=[3, 9, 25])
(ROOT / 'product39.json').write_text(json.dumps(config, indent=2) + '\n')
print(json.dumps({'head': HEAD, 'base': BASE, 'files': len(files), 'web': files['openscrub_web.py'], 'config312_sha256': hashlib.sha256((ROOT / 'product312.json').read_bytes()).hexdigest()}, indent=2))
