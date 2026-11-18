"""Source-only metadata collector. Never imports or executes product code."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib

REPO = Path('/home/tahv0/src/OpenScrub')
OUT = REPO / '.superpowers/sdd/README/review-filter-implementation-readiness-evidence'
BASE = '2ae3257b9752e2d976ff7a0d39955a13c133273a'
COMBINED = 'c205ef5379778f63313b519411a2d5e37d07cba5'


def git(*args):
    return subprocess.check_output(['git', '-C', str(REPO), *args])


def blob(pin, path):
    return git('show', pin + ':' + path)


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')


paths = ['openscrub.py', 'openscrub_web.py', 'zones_ui.py',
         'openscrub_setup.py', 'openscrub_update.py', 'openscrub_vault.py',
         'test_openscrub.py', 'tests/test_review_choices.py',
         'tests/test_review_save_failures.py', 'pyproject.toml']
identities = []
for path in paths:
    raw = blob(BASE, path)
    row = dict(path=path, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    if path.endswith('.py'):
        tree = ast.parse(raw)
        tests = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name.startswith('test_')]
        row['test_functions'] = len(tests)
        cases = 0
        for node in tests:
            count = 1
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) \
                        and decorator.func.attr == 'parametrize':
                    count *= len(ast.literal_eval(decorator.args[1]))
            cases += count
        row['literal_parameterized_cases'] = cases
    identities.append(row)

sizes = {}
for line in git('ls-tree', '-r', '--long', BASE).decode().splitlines():
    info, path = line.split('\t')
    sizes[path] = int(info.split()[3])
project = tomllib.loads(blob(BASE, 'pyproject.toml').decode())
targets = project['tool']['hatch']['build']['targets']
sdist = {p: s for p, s in sizes.items() if any(p == i or p.startswith(i)
         for i in targets['sdist']['include'])}
wheel = targets['wheel']['include'] + list(targets['wheel']['force-include'])
write('source-identities.json', {
    'mode': 'source-only; no acceptance execution', 'base': BASE,
    'base_tree': git('show', '-s', '--format=%T', BASE).decode().strip(),
    'combined_context_only': COMBINED,
    'combined_web_sha256': hashlib.sha256(blob(COMBINED, 'openscrub_web.py')).hexdigest(),
    'files': identities,
    'whole_tree_payload_bytes': sum(sizes.values()),
    'sdist_declared_payload_bytes': sum(sdist.values()),
    'sdist_automatic_pyproject_bytes': sizes['pyproject.toml'],
    'sdist_declared_files': sdist,
    'wheel_declared_payload_bytes': sum(sizes[p] for p in wheel),
    'limits': 'Payload sums exclude archive headers/compression, metadata, build backend, installation, bytecode, profiles, logs and temporary coexistence. Not disk-peak bounds.'})

anchors = {
    'openscrub_web.py': [(1132, 1149), (2085, 2118), (2155, 2177),
                          (2280, 2299), (2343, 2378), (2556, 2589),
                          (2730, 2737), (2782, 2971), (2995, 3075)],
    'test_openscrub.py': [(28, 36), (227, 240), (375, 398),
                          (676, 724), (957, 1027), (1177, 1189),
                          (2163, 2180), (2327, 2346), (3963, 3990)],
    'openscrub_vault.py': [(29, 39), (109, 137)]}
collected = []
for path, ranges in anchors.items():
    lines = blob(BASE, path).decode().splitlines()
    for start, end in ranges:
        collected.append(dict(pin=BASE, path=path, start=start, end=end,
                              text='\n'.join(f'{i}: {lines[i-1]}' for i in range(start, end+1))))
lines = blob(COMBINED, 'openscrub_web.py').decode().splitlines()
for start, end in [(4120, 4153), (4205, 4213), (4504, 4536)]:
    collected.append(dict(pin=COMBINED, path='openscrub_web.py', start=start, end=end,
                          text='\n'.join(f'{i}: {lines[i-1]}' for i in range(start, end+1))))
write('interface-anchors.json', collected)

docs = ['review-filter-implementation-readiness-brief.md', 'review-filters-source-plan.md',
        'review-filter-scope-research.md', 'task-20-brief.md', 'task-20-report.md',
        'task-20-review.md', 'verification-environment-handoff.md',
        'task-9-report.md', 'task-9-fix1-report.md', 'task-164-report.md',
        'review-choices-baseline-research.md', 'task9-evidence/README.md',
        'task9-evidence/manifest.json', 'task9-evidence/scripts/serve.py',
        'task9-evidence/scripts/qa.cjs', 'task9-evidence/scripts/check_output.py',
        'review-choices-baseline-evidence/emit.py',
        'review-choices-baseline-evidence/browser.cjs']
records = []
for name in docs:
    raw = (REPO / '.superpowers/sdd/README' / name).read_bytes()
    records.append(dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
name = 'docs/superpowers/plans/upstream-delivery/execution/tooling/README.md'
raw = (REPO / name).read_bytes()
records.append(dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
write('read-document-identities.json', records)
print(json.dumps({'source_only': True, 'metadata_files': 3,
                  'output_bytes': sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())}))
