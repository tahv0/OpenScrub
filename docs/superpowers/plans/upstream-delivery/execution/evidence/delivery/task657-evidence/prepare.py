from pathlib import Path
import hashlib,json,subprocess,sys
E=Path(__file__).parent;R=E.parent;S=Path('/home/tahv0/.codex/worktrees/bde3/OpenScrub')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(*a):return subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false',*a],cwd=S,text=True).strip()
old=json.loads((R/'task655-evidence/package-312.json').read_text()); files={p:sha(S/p) for p in git('ls-files').splitlines() if (S/p).is_file()};modules=old['modules'];assert len(modules)==12
pins=[p for p in old['prerequisites'] if '/task' not in p['path'] or 'runtime/task1203' in p['path']]
helper=R.parents[2]/'docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py'
pins.append({'path':str(helper),'sha256':'354cf49b0c83d11f3945137fbdffc3ac6b2793f1217ac39a9b62270097940067'})
for p in pins:assert sha(p['path'])==p['sha256'],p
for label,exe,ver in [('312','/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python',[3,12,16]),('39','/tmp/openscrub-python39-20261117/venv/bin/python',[3,9,25])]:
 expected=json.loads((R/f'task656-evidence/interpreter-{label}.json').read_text())['executable_sha256'];assert sha(exe)==expected
 config=dict(task='task657',scratch=str(R/'runtime/task657/runs'),source=str(S),source_kind='git',base='d1eeebd2b12645a7284344fb16ec589c8aba0ce7',head=git('rev-parse','HEAD'),policy='development' if '--development' in sys.argv else 'frozen',files=files,modules=modules,python=exe,python_version=ver,min_free_bytes=2000000000,configure_app=True,prerequisites=pins+[dict(path=exe,sha256=expected,executable=True)],environment=old['environment'],excluded_paths=['/home/tahv0/src/OpenScrub',str(S)])
 (E/f'config-{label}.json').write_text(json.dumps(config,indent=2)+'\n')
(E/'source-identities.json').write_text(json.dumps(dict(head=git('rev-parse','HEAD'),files=files,modules=modules),indent=2)+'\n')
print('Frozen prospective identities:',len(files),'files;',len(modules),'modules')
