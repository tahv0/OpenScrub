import hashlib,json,os,signal,socket,subprocess,sys,time,urllib.request
from pathlib import Path
art=Path('/tmp/openscrub-task164');site=art/'installed/site-packages'
assert Path.cwd()==art
import openscrub,openscrub_web as web
assert Path(openscrub.__file__).parent==site
assert Path(web.__file__).parent==site
assert str(art/'installed-profile') in web.JOBS_DIR
native=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
for name in ['openscrub.py','openscrub_web.py','zones_ui.py']:
 assert (site/name).read_bytes()==(native/name).read_bytes()
a=openscrub.build_parser().parse_args(['synthetic.mp4'])
b=web.build_args(dict(video='synthetic.mp4',options={},dir=str(art/'installed-defaults')))
for value in [a,b]:assert (value.mode,value.pad,value.coverage)==('blur',8,'tight')
cli=subprocess.run([str(site/'bin/openscrub'),'--help'],text=True,capture_output=True,check=True)
assert 'usage:' in cli.stdout;(art/'installed-cli-help.txt').write_text(cli.stdout)
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
with (art/'installed-web.log').open('w') as log:
 p=subprocess.Popen([str(site/'bin/openscrub-web'),'--http','--host','127.0.0.1','--port',str(port),'--retain-days','0'],cwd=art,stdout=log,stderr=subprocess.STDOUT)
 try:
  for _ in range(150):
   try:
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/jobs',timeout=.5) as r:assert json.load(r)==[]
    break
   except OSError:
    assert p.poll() is None;time.sleep(.1)
  else:raise TimeoutError('installed web')
  with urllib.request.urlopen(f'http://127.0.0.1:{port}/') as r:assert b'OpenScrub' in r.read()
 finally:
  p.send_signal(signal.SIGTERM)
  try:p.wait(timeout=8)
  except subprocess.TimeoutExpired:p.kill();p.wait();raise
 assert p.returncode==0
result={'python':sys.version,'imports':[openscrub.__file__,web.__file__],'profile':web.JOBS_DIR,'cli_help':True,'real_web_entrypoint':True,'homepage_jobs':True,'default_mask_pad_coverage':['blur',8,'tight'],'idle_sigterm':p.returncode}
(art/'installed-smoke.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
