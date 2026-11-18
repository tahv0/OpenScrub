from pathlib import Path
import json,hashlib,subprocess,tomllib
w=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
r=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task654')
e=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',str(w),*args])
cfg=json.loads((r/'preflight-config-312.json').read_text());cfg['head']=git('rev-parse','HEAD').decode().strip()
tracked=git('ls-tree','-r','--name-only',cfg['head']).decode().splitlines()
files=[f for f in tracked if f.endswith(('.py','.js','.cjs','.toml','.md','.json','.spec')) or f.startswith('Dockerfile') or f in ['LICENSE','NOTICE','requirements.txt','assets/openscrub.ico']]
cfg['files']={f:hashlib.sha256(git('show',cfg['head']+':'+f)).hexdigest() for f in files}
cfg['modules']['openscrub_internal.job_logs']='openscrub_internal/job_logs.py'
cfg['prerequisites'] += [{'path':str(p),'sha256':sha(p)} for p in [e/'adapters/roundtrip_stdout_selected.py',e/'adapters/audit.py',Path('/usr/bin/node')]]
for label,python,version in [('312',cfg['python'],[3,12,16]),('39','/tmp/openscrub-python39-20261117/venv/bin/python',[3,9,25])]:
 c=dict(cfg,python=python,python_version=version)
 (r/('frozen-'+label+'.json')).write_text(json.dumps(c,indent=2)+'\n')
browser=dict(cfg);browser['environment']=dict(cfg['environment'],NODE_PATH='/tmp/openscrub-save-as-20261116/node_modules',PLAYWRIGHT_BROWSERS_PATH='/tmp/openscrub-save-as-20261116/browsers',OPENSCRUB_PLAYWRIGHT_MODULE='/tmp/openscrub-save-as-20261116/node_modules/playwright',OPENSCRUB_CHROMIUM='/tmp/openscrub-save-as-20261116/browsers/chromium_headless_shell-1255/chrome-headless-shell-linux64/chrome-headless-shell')
for p in [Path(browser['environment']['OPENSCRUB_CHROMIUM']),Path(browser['environment']['NODE_PATH'])/'playwright/package.json',Path(browser['environment']['NODE_PATH'])/'playwright-core/package.json']:
 browser['prerequisites'].append({'path':str(p),'sha256':sha(p)})
(r/'browser-312.json').write_text(json.dumps(browser,indent=2)+'\n')
tools=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1203/build-tools')
bootstrap=Path('/tmp/openscrub-baseline-20261116/bootstrap/lib/python3.14/site-packages')
package=dict(cfg);package['prerequisites']=list(cfg['prerequisites'])+[{'path':str(p),'sha256':sha(p)} for p in [tools/'hatchling/build.py',tools/'tomlkit/__init__.py',bootstrap/'pip/__main__.py',e/'adapters/listening_smoke.py']]
includes=tomllib.loads((w/'pyproject.toml').read_text())['tool']['hatch']['build']['targets']['sdist']['include']
sdist=[f for f in files if f=='pyproject.toml' or f in includes or any(f.startswith(d.rstrip('/')+'/') for d in includes)]
package['package']={'tool_paths':[str(tools),str(bootstrap)],'sdist_files':sorted(sdist),'wheel_files':sorted(set(cfg['modules'].values())|{'plate_models.json','face_models.json','person_models.json'}),'requires_python':'>=3.9','installed_commands':[['{target}/bin/openscrub','--help'],['{target}/bin/openscrub-web','--help'],[str(e/'adapters/audit.py')],[str(e/'adapters/listening_smoke.py'),'{target}']]}
package['excluded_paths']=[str(w),'/home/tahv0/src/OpenScrub']
(r/'package-312.json').write_text(json.dumps(package,indent=2)+'\n')
(e/'source-identities.json').write_text(json.dumps(dict(head=cfg['head'],base=cfg['base'],files=cfg['files'],modules=cfg['modules']),indent=2)+'\n')
for p in r.glob('*.json'):
 (e/p.name).write_bytes(p.read_bytes())
print(cfg['head'],len(files),'frozen source identities')
