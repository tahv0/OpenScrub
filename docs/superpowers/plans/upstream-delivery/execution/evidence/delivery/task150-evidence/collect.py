"""Compact, task-only evidence: no media, installations, exports or local policy."""
from pathlib import Path
import ast,hashlib,json,os,platform,shutil,subprocess
E=Path(__file__).parent;R=E.parent/'runtime/task150/runs';S=Path('/home/tahv0/.codex/worktrees/bde3/OpenScrub')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
runids=['red-js01','red-browser01','green-js01','green-browser01','green-js02','green-browser02','full01','floor01','browser-accept01','touch01','http01','package01']
records=[]
for name in runids:
 run=R/name;dest=E/'runs'/name;dest.mkdir(parents=True,exist_ok=True)
 for p in [run/'preflight.json',*run.glob('runtime-*.json'),*sorted((run/'logs').glob('*.log')),run/'browser-results.json',run/'touch-precondition.json',run/'http-results.json',run/'output-check.json',run/'initial-report.json',run/'pre-render-report.json',run/'package-identities.json']:
  if p.is_file():shutil.copyfile(p,dest/p.name)
 records.append(dict(id=name,preflight=json.loads((run/'preflight.json').read_text()),logs={p.name:sha(p) for p in (dest).glob('*.log')}))
# Two selected viewport screenshots show rendered controls and help, without media exports.
for name,path in [('mobile-controls.png',R/'browser-accept01/mobile.png'),('mobile-help.png',R/'touch01/filtered.png')]:shutil.copyfile(path,E/name)
(E/'runs.json').write_text(json.dumps(records,indent=2)+'\n')
# Compare the final code/test inventory to the full/floor-tested commit.
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=S,text=True).strip();tested='ac28a2ac981f2612cbaeadedddbfac8db1efeefb'
base='2ae3257b9752e2d976ff7a0d39955a13c133273a';config=json.loads((E/'frozen.json').read_text())
identity=dict(base=base,full_floor_head=tested,head=head,files=config['files'],full_floor_changes=subprocess.check_output(['git','diff','--stat',tested,head],cwd=S,text=True),product_unchanged_since_full={p:sha(S/p)==hashlib.sha256(subprocess.check_output(['git','show',tested+':'+p],cwd=S)).hexdigest() for p in config['modules'].values()},engine_defaults_unchanged_from_base=sha(S/'openscrub.py')==hashlib.sha256(subprocess.check_output(['git','show',base+':openscrub.py'],cwd=S)).hexdigest())
for n in ['APP_JS','APP_CSS']:
 tree=ast.parse((S/'openscrub_web.py').read_text());v=next(ast.literal_eval(x.value) for x in tree.body if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id==n for t in x.targets));identity[n+'_sha256']=hashlib.sha256(v.encode()).hexdigest()
(E/'source-identities.json').write_text(json.dumps(identity,indent=2)+'\n')
# This audit is expressly POST-RUN; old configs/logs are preserved, not rewritten.
pin=E.parent/'task655-evidence/package-312.json';previous=json.loads(pin.read_text())
paths=[d for d in previous['prerequisites'] if ('/tools/' in d['path'] or '/usr/bin/node'==d['path'] or '/browsers/' in d['path'] or '/node_modules/' in d['path'] or '/build-tools/' in d['path'] or '/pip/__main__.py' in d['path'])]
checks=[]
for d in paths:
 p=Path(d['path']);actual=sha(p);assert actual==d['sha256'],(p,actual,d['sha256']);checks.append(dict(path=str(p),resolved=str(p.resolve()),expected=d['sha256'],actual=actual,match=True))
helper=E.parent.parent.parent.parent/'docs/superpowers/plans/upstream-delivery/execution/tooling'
helper=Path('/home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling')
helperpins=json.loads((E.parent/'task1631-evidence/helper-identities.json').read_text())
for name,expected in helperpins.items():assert sha(helper/name)==expected
interpreters=[]
for path,past in [('/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python','environment-312.json'),('/tmp/openscrub-python39-20261117/venv/bin/python','environment-39.json')]:
 p=Path(path);old=E.parent/'task655-evidence'/past;observed=json.loads(subprocess.check_output([path,'-I','-B','-c','import json,sys;from importlib import metadata;print(json.dumps(dict(executable=sys.executable,python=sys.version,versions={n:metadata.version(n) for n in ["opencv-python","numpy","Flask","Pillow","cheroot","pytest"]})))'],text=True));prior=json.loads(old.read_text());assert observed['python']==prior['python'] and observed['executable']==prior['executable'] and observed['versions']==prior['versions'];bytepin=E.parent/'task656-evidence'/('interpreter-312.json' if 'opencv4' in path else 'interpreter-39.json');expected=json.loads(bytepin.read_text())['executable_sha256'];assert sha(p)==expected
 interpreters.append(dict(path=path,resolved=str(p.resolve()),sha256=sha(p),observed=observed,prior_version_pin=dict(file=str(old),sha256=sha(old)),prior_binary_pin=dict(file=str(bytepin),file_sha256=sha(bytepin),expected_executable_sha256=expected,match=True,mtime_utc=__import__('datetime').datetime.fromtimestamp(bytepin.stat().st_mtime,__import__('datetime').timezone.utc).isoformat())))
env=dict(os.environ,LD_LIBRARY_PATH='/tmp/openscrub-baseline-20261116/tools/usr/lib/x86_64-linux-gnu:/tmp/openscrub-baseline-20261116/tools/usr/lib/x86_64-linux-gnu/pulseaudio:/tmp/openscrub-save-as-20261116/tools/usr/lib/x86_64-linux-gnu')
versions={}
for path,args in [('/usr/bin/node',['--version']),('/tmp/openscrub-baseline-20261116/tools/usr/bin/ffmpeg',['-version']),('/tmp/openscrub-baseline-20261116/tools/usr/bin/ffprobe',['-version']),('/tmp/openscrub-baseline-20261116/tools/usr/bin/tesseract',['--version']),('/tmp/openscrub-save-as-20261116/browsers/chromium_headless_shell-1255/chrome-headless-shell-linux64/chrome-headless-shell',['--version'])]:
 r=subprocess.run([path,*args],env=env,text=True,capture_output=True,check=True);versions[path]=r.stdout+r.stderr
summary=dict(boundary='Post-run identity audit; these native-tool byte hashes were not Task150 preflight-enforced. No shared tool/environment mutations were performed. Prior configs/logs remain unchanged.',platform=platform.platform(),prior_native_pin=dict(file=str(pin),sha256=sha(pin),mtime_utc=__import__('datetime').datetime.fromtimestamp(pin.stat().st_mtime,__import__('datetime').timezone.utc).isoformat()),tools=checks,interpreters=interpreters,versions=versions,helper_matches=helperpins)
(E/'post-run-tool-audit.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(dict(native_tools=len(checks),interpreters=[x['observed'] for x in interpreters],versions={k:v.splitlines()[0] for k,v in versions.items()}),indent=2))
