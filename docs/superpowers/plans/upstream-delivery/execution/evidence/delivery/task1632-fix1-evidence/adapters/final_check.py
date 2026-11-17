"""Read-only source/evidence binding after the scoped fix acceptance gates."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

root = Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README')
evidence = root / 'task1632-fix1-evidence'
source = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
config = json.loads((evidence / 'frozen.json').read_text())
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
assert head == config['head']
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=source, text=True).strip()
for name, expected in config['files'].items():
    actual = (source / name).read_bytes()
    committed = subprocess.check_output(['git', 'show', head + ':' + name], cwd=source)
    assert hashlib.sha256(actual).hexdigest() == expected and actual == committed
before_text = subprocess.check_output(['git', 'show', config['base'] + ':openscrub.py'], cwd=source, text=True)
after_text = (source / 'openscrub.py').read_text()
before, after = ast.parse(before_text), ast.parse(after_text)
def dump(node):
    return ast.dump(node, include_attributes=False)
assert len(before.body) == len(after.body)
changed = []
for old, new in zip(before.body, after.body):
    if dump(old) != dump(new):
        assert isinstance(old, ast.FunctionDef) and isinstance(new, ast.FunctionDef)
        assert old.name == new.name
        changed.append(old.name)
assert changed == ['render_hdr', 'render']
selected = {'subprocess.Popen', 'cv2.VideoCapture', 'cv2.VideoWriter', '_blur_yuv10',
            '_blur_silhouette_yuv10', 'blur_region', 'blur_silhouette', 'cv2.rectangle',
            'cv2.polylines', 'cv2.putText', '_out_q', '_rate_cap_args',
            'audio_ffmpeg_args', '_ffmpeg_failure'}
contracts = {}
for name in ('render', 'render_hdr'):
    old = next(n for n in before.body if isinstance(n, ast.FunctionDef) and n.name == name)
    new = next(n for n in after.body if isinstance(n, ast.FunctionDef) and n.name == name)
    assert dump(old.args) == dump(new.args)
    def calls(fn):
        return sorted(dump(n) for n in ast.walk(fn)
                      if isinstance(n, ast.Call) and ast.unparse(n.func) in selected)
    assert calls(old) == calls(new)
    def removal(fn):
        return [dump(n) for n in ast.walk(fn)
                if isinstance(n, ast.If) and isinstance(n.test, ast.Name)
                and n.test.id == 'remove_partial']
    assert removal(old) == removal(new) and len(removal(new)) == 1
    def removal_sites(fn):
        result = []
        def visit(node, parents):
            if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                    and node.value.value is True and any(isinstance(t, ast.Name)
                    and t.id == 'remove_partial' for t in node.targets)):
                branch = next(n for n in reversed(parents) if isinstance(n, (ast.If, ast.ExceptHandler)))
                result.append((type(branch).__name__, ast.unparse(
                    branch.test if isinstance(branch, ast.If) else branch.type)))
            for child in ast.iter_child_nodes(node):
                visit(child, parents + [node])
        visit(fn, [])
        return sorted(result)
    assert removal_sites(old) == removal_sites(new) and len(removal_sites(new)) == 2
    contracts[name] = dict(public_args_defaults_equal=True, selected_original_calls_equal=True,
                           removal_block_equal=True, recognized_removal_sites=removal_sites(new))
identity = json.loads((root / 'task1632-evidence/helper-identity.json').read_text())
repo = Path('/home/tahv0/src/OpenScrub')
for name, expected in identity['files'].items():
    assert hashlib.sha256((repo / name).read_bytes()).hexdigest() == expected['sha256']
shutil.copyfile(root / 'task1632-evidence/helper-identity.json', evidence / 'helper-identity.json')
run_index = {}
for run in sorted((root / 'runtime/task1632/runs').glob('fix1-*')):
    destination = evidence / 'runs' / run.name
    destination.mkdir(parents=True, exist_ok=True)
    for path in list(run.glob('*.json')) + list((run / 'logs').glob('*.log')):
        dest = destination / path.relative_to(run)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
    run_index[run.name] = []
    for path in sorted((destination / 'logs').glob('*.log')):
        text = path.read_text(errors='replace')
        run_index[run.name].append(dict(file=str(path.relative_to(evidence)), bytes=path.stat().st_size,
                                       sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                       summaries=[line for line in text.splitlines() if ' passed' in line or ' failed' in line or line.startswith('SERVER_CLEANUP')]))
(evidence / 'run-index.json').write_text(json.dumps(run_index, indent=2) + '\n')
subprocess.run(['git', 'diff', '--check'], cwd=source, check=True)
(evidence / 'final-check.json').write_text(json.dumps(dict(
    base=config['base'], head=head, clean=True, selected_files_equal_git=len(config['files']),
    production_sha256=config['files']['openscrub.py'], tests_sha256=config['files']['tests/test_render_resources.py'],
    only_changed_runtime_functions=changed, child_shutdown_helper_unchanged=True,
    shared_tooling_unchanged=True, contracts=contracts,
    historical_full_suite=dict(head='e9fd0d39bd9c10ddbaa121e9c91cc504921c5afb', current_source=False,
                               result='174 passed, 5 historical inapplicable skips; not repeated in fix1'),
), indent=2) + '\n')
print('final committed source, unchanged boundaries/tooling, and compact evidence verified')
