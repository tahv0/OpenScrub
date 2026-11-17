"""Replay the review's tiny dummy-source checks; no product import or suite."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

root = Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task901') / ('review-' + uuid.uuid4().hex)
root.mkdir()
source = root / 'source'
source.mkdir()
adapter = root / 'adapter'
adapter.mkdir()
scratch = root / 'runs'
scratch.mkdir()
(source / 'sample.py').write_text('VALUE = 17\n')
(source / '.verification-source.json').write_text(json.dumps({'base': 'fixture-base', 'head': 'fixture-head'}))
(adapter / 'sample.py').write_text('VALUE = 99\n')
(adapter / 'probe.py').write_text('import json, sample\nprint("REVIEW_PROBE " + json.dumps({"origin": sample.__file__, "value": sample.VALUE}))\n')
py = '/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python'
cfg = {'task': 'task901-review', 'scratch': str(scratch), 'source': str(source), 'source_kind': 'export', 'base': 'fixture-base', 'head': 'fixture-head', 'policy': 'frozen', 'files': {'sample.py': hashlib.sha256((source / 'sample.py').read_bytes()).hexdigest()}, 'modules': {'sample': 'sample.py'}, 'python': py, 'python_version': [3, 12, 16], 'min_free_bytes': 1, 'configure_app': False}
config = root / 'config.json'
config.write_text(json.dumps(cfg))
tool = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py')
command = [py, '-I', str(tool), '--config', str(config), '--run-id', 'script-origin', 'run', '--', str(adapter / 'probe.py')]
result = subprocess.run(command, capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
(root / 'script-origin-transcript.log').write_text(result.stdout + result.stderr)
print('REVIEW_ROOT', root)
print('PROBE_EXIT', result.returncode)
print(result.stdout)
print(result.stderr)
# Execute only this stdlib command-construction function; never launch pytest.
node = next(n for n in ast.parse(tool.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'python_command')
namespace = {'require': lambda condition, message: None if condition else (_ for _ in ()).throw(ValueError(message))}
exec(compile(ast.Module(body=[node], type_ignores=[]), '<review-argument-probe>', 'exec'), namespace)
for args in [['-B', '-m', 'pytest', 'fixture.py', '-n', '2'], ['-Es', '-c', 'pass']]:
    try:
        print('ARGUMENT_PROBE', json.dumps(namespace['python_command'](cfg, scratch / 'argument-probe', args)))
    except ValueError as error:
        print('ARGUMENT_REJECTED', str(error))
