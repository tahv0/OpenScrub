"""Retain compact task-owned logs/identities only; never copy runtime/media trees."""
from pathlib import Path
import hashlib
import json
import re
import shlex
import shutil
import subprocess

E = Path(__file__).resolve().parents[1]
R = E.parent / 'runtime/task654'
W = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
T = W / 'tests'
A = E / 'adapters'
H = Path('/home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling')

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def git(*args):
    return subprocess.check_output(['git', '-C', str(W), *args])

owners = ['test_job_logs.py', 'test_job_filename_display.py', 'test_job_polling_node.py',
          'test_thumbnail_scheduling.py', 'test_review_choices.py', 'test_review_save_failures.py',
          'test_export_save_as.py', 'test_job_lifecycle.py', 'test_job_response_lifetime.py',
          'test_job_source_allowlist_lifecycle.py', 'test_report_transactions.py',
          'test_report_serialization.py', 'test_report_roundtrip.py', 'test_manual_addition_replay.py']
teardown = ['test_browser_composition.py::test_retaining_panel_keeps_editor_owner_and_gesture',
            'test_browser_composition.py::test_successful_render_removal_releases_editor_owner']
combo = 'test_browser_composition.py::test_combined_real_page_owner_interactions'
default = 'test_browser_composition.py::test_tiny_actual_default_sdr_control'
actions = 'test_job_polling_node.py::test_phase_actions_replacement_releases_only_removed_editor_owner'
roundtrip_args = ['-o', 'pythonpath=' + str(A), '-p', 'roundtrip_stdout_selected']
browser_args = ['-o', 'pythonpath=' + str(A), '-p', 'browser_setup']
def tests(names, extra=()):
    return ['-B', '-m', 'pytest'] + [str(T / n) for n in names] + list(extra) + ['-q']

specs = [
 ('task654-initial-preflight', 'preflight-config-312.json', 'preflight', [], 0, 'supervisor initial source inventory; pre-composition'),
 ('task654-teardown-red-01', 'composition-red-312.json', 'run', tests(['test_browser_composition.py']), 1, '2 genuine failures; unchanged seven-pick runtime'),
 ('task654-teardown-green-01', 'teardown-green-development.json', 'run', tests(teardown), 0, '2 passed; development policy'),
 ('task654-owners-312-01', 'frozen-312.json', 'run', tests(owners + teardown, roundtrip_args), 1, '346 passed / 9 fixture failures'),
 ('task654-fixtures-312-02', 'frozen-312.json', 'run', tests(owners[:3]), 1, '47 passed / 7 remaining fixture failures'),
 ('task654-fixtures-312-03', 'frozen-312.json', 'run', tests(owners[:2]), 0, '20 passed'),
 ('task654-owners-39-01', 'frozen-39.json', 'run', tests(owners + teardown, roundtrip_args), 0, '355 passed actual3.9; before final phase-actions fix'),
 ('task654-actions-red-01', 'frozen-312.json', 'run', tests([actions]), 1, '1 genuine failure; pre-fix runtime'),
 ('task654-actions-green-01', 'actions-green-development.json', 'run', tests(['test_job_polling_node.py'] + teardown), 0, '37 passed; development policy'),
 ('task654-polling-39-02', 'frozen-39.json', 'run', tests(['test_job_polling_node.py'] + teardown), 0, '37 passed actual3.9; final runtime bytes'),
 ('task654-browser-312-01', 'browser-312.json', 'run', tests(['test_job_polling_browser.py', 'test_browser_log_retention.py', combo, default]), 1, '9 setup failures / 1 actual defaultSDR pass'),
 ('task654-browser-312-02', 'browser-corrected-312.json', 'run', tests(['test_job_polling_browser.py', 'test_browser_log_retention.py', combo], browser_args), 1, '8 passed / 1 offscreen-card fixture failure'),
 ('task654-polling-browser-03', 'browser-final-312.json', 'run', tests(['test_job_polling_browser.py::test_emitted_page_polling_acceptance'], browser_args), 1, '1 paused-clock fixture failure after explicit scroll'),
 ('task654-audit-source-312', 'frozen-312.json', 'run', ['-B', str(A / 'audit.py')], 0, '71 source defaults / exact PAGE / Node --check'),
 ('task654-polling-browser-04', 'browser-final-312.json', 'run', tests(['test_job_polling_browser.py::test_emitted_page_polling_acceptance'], browser_args), 0, '1 passed; explicit rAF clock advancement'),
 ('task654-package-312-01', 'package-312.json', 'package', [], 0, '74 sdist + extracted / 14 wheel members; installed CLI/web/listening/defaults'),
 ('task654-audit-source-39', 'frozen-39.json', 'run', ['-B', str(A / 'audit.py')], 0, 'actual3.9 final source/default/environment/Node --check'),
]
commands = []
for rid, config, action, argv, code, result in specs:
    source = R / 'runs' / rid
    target = E / 'runs' / rid
    target.mkdir(parents=True, exist_ok=True)
    for p in source.iterdir():
        if p.is_file() and (p.name == 'preflight.json' or p.name == 'package-identities.json' or p.name.startswith('runtime-')):
            shutil.copyfile(p, target / p.name)
    for sub in ['logs', 'browser']:
        folder = source / sub
        if not folder.is_dir():
            continue
        for p in folder.iterdir():
            if p.is_file() and p.suffix in {'.json', '.log', '.stdout', '.stderr', '.png'}:
                dest = target / sub / p.name
                dest.parent.mkdir(exist_ok=True)
                shutil.copyfile(p, dest)
    preflight = json.loads((source / 'preflight.json').read_text())
    forwarded = ['--config', str(R / config), '--run-id', rid, action]
    if argv:
        forwarded += ['--'] + argv
    commands.append(dict(run=rid, forwarded_argv=forwarded, workload=argv, exit=code, result=result,
                         head=preflight['head'], policy=preflight['policy'], python=preflight.get('python'),
                         preflight_sha256=sha(target/'preflight.json'),
                         source_files=preflight['files'], logs={str(p.relative_to(target)):sha(p) for p in target.rglob('*') if p.is_file() and p.suffix=='.log'}))
(E / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
lines = ['# Recorded Task654 verification argv', '',
         'Every allocating invocation used bounded external development admission. The following are the exact forwarded arguments to the unchanged reviewed launcher, not a bypass recipe. Clean explicit prepared3.12 controller, login:false; socket/browser/listening escalation was selected at the original invocation. Private local admission tooling, policy, config and receipts are excluded.', '',
         'Config filenames were refreshed as source evolved. Each run directory retains its actual immutable preflight and generated runtime config; those records bind that attempt, rather than the later file now at an argument path.', '']
for c in commands:
    lines += ['## '+c['run'], '', '`'+c['head']+'`; '+c['policy']+'; exit '+str(c['exit'])+'; '+c['result'], '',
              '```text', shlex.join([str(H/'verify.py')] + c['forwarded_argv']), '```', '']
(E/'commands.md').write_text('\n'.join(lines))

mapping=[]
for n,commit in enumerate(git('log','--reverse','--format=%H','117e41ac..HEAD').decode().splitlines(),1):
    body=git('show','-s','--format=%B',commit).decode()
    original=re.search(r'cherry picked from commit ([0-9a-f]{40})',body)
    mapping.append(dict(original=original[1] if original else None, composed=commit, subject=body.splitlines()[0]))
    (E/'assembly'/('%02d-'%n+commit[:7]+'.patch')).write_bytes(git('show','--format=fuller',commit))
(E/'assembly/original-to-composed.json').write_text(json.dumps(mapping,indent=2)+'\n')
(E/'assembly/combined-resolution.patch').write_bytes(git('diff','117e41ac..HEAD','--','openscrub_web.py','Dockerfile','Dockerfile.cuda','Dockerfile.intel','pyproject.toml','openscrub_internal/__init__.py'))
# Exact old/new fixtures remain available even if their original source branch
# is later rebased. Product source patches and every changed fixture are retained.
fixture_revisions=['0d8df87','fb9d59b','61dbb31','a3d0f0d','20d9f29','46a5b42','a4649a2','6697883','00480c7']
fixture_files=['tests/test_job_logs.py','tests/test_job_filename_display.py','tests/test_job_polling_node.py',
               'tests/test_job_polling_browser.py','tests/test_thumbnail_scheduling.py','tests/test_browser_composition.py',
               'tests/test_browser_composition.cjs','tests/test_review_save_failures.py']
identities=[]
for rev in fixture_revisions:
    for name in fixture_files:
        try:
            data=git('show',rev+':'+name)
        except subprocess.CalledProcessError:
            continue
        dest=E/'fixtures'/rev/name
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        identities.append(dict(revision=rev,file=name,sha256=sha(dest)))
(E/'fixture-identities.json').write_text(json.dumps(identities,indent=2)+'\n')
for name, run in [('environment312.json','task654-audit-source-312'),('environment39.json','task654-audit-source-39')]:
    shutil.copyfile(R/'runs'/run/'logs/audit-source.json',E/name)
shutil.copyfile(R/'runs/task654-package-312-01/logs/audit-installed.json',E/'installed-audit.json')
shutil.copyfile(R/'runs/task654-package-312-01/package-identities.json',E/'package-identities.json')
# Explicit source/recipe preservation and byte comparison across reused gates.
head=git('rev-parse','HEAD').decode().strip()
base='117e41ac5ee857a6b367caf6ccbd479d78989ff2'
recipes=['Dockerfile','Dockerfile.cuda','Dockerfile.intel','pyproject.toml','openscrub_update.py','windows/openscrub.spec']
static={p:dict(sha256=hashlib.sha256(git('show',head+':'+p)).hexdigest(),unchanged_from_base=git('show',head+':'+p)==git('show',base+':'+p)) for p in recipes}
(E/'static-recipes.json').write_text(json.dumps(static,indent=2)+'\n')
checks={'head':head,'branch':git('branch','--show-current').decode().strip(),'base':base,
        'core_ref':git('rev-parse','integration/upstream-focused').decode().strip(),
        'status':git('status','--porcelain').decode(),'diff_check':subprocess.run(['git','-C',str(W),'diff','--check',base+'..HEAD'],capture_output=True,text=True).returncode,
        'helper':{p.name:sha(p) for p in H.glob('*.py')},
        'final_runtime':{p:hashlib.sha256(git('show',head+':'+p)).hexdigest() for p in ['openscrub.py','openscrub_web.py','openscrub_internal/job_logs.py']},
        'runtime_change_after_floor':git('diff','20d9f29..HEAD','--','openscrub_web.py').decode(),
        'runtime_unchanged_after_a4649a2':git('diff','a4649a2..HEAD','--','openscrub_web.py').decode()==''}
assert checks['status']=='' and checks['diff_check']==0
(E/'self-review.json').write_text(json.dumps(checks,indent=2)+'\n')
print('retained',len(commands),'verification invocations;',len(mapping),'commits;',len(identities),'exact fixture snapshots')
