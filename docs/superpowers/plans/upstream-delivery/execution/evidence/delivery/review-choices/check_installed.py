import json,os,signal,socket,subprocess,time,urllib.request
from pathlib import Path
art=Path('/tmp/openscrub-task20');site=art/'installed/site-packages'
env=dict(os.environ,PYTHONPATH=str(art/'installed-hooks')+':'+str(site),OPENSCRUB_NO_AUTOFETCH='1',PYTHONDONTWRITEBYTECODE='1')
python='/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python'
probe=subprocess.run([python,'-c', '''import json,openscrub,openscrub_web as w; a=openscrub.build_parser().parse_args(['synthetic.mp4']); b=w.build_args(dict(video='synthetic.mp4',options={},dir='/tmp/openscrub-task20/installed-defaults')); assert (a.engine,a.device,a.encoder,a.mode,a.pad,a.coverage,a.out_quality)==('auto','auto','auto','blur',8,'tight','archival'); assert (b.engine,b.device,b.encoder,b.mode,b.pad,b.coverage,b.out_quality)==('auto','auto','auto','blur',8,'tight','archival'); print(json.dumps({'engine':openscrub.__file__,'web':w.__file__,'data':w.JOBS_DIR}))'''],cwd=art,env=env,text=True,capture_output=True,check=True)
info=json.loads(probe.stdout);assert str(site) in info['engine'] and str(site) in info['web'];assert str(art/'installed-profile') in info['data']
for name in ['openscrub.py','openscrub_web.py','zones_ui.py']:assert (site/name).read_bytes()==(Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')/name).read_bytes()
cli=subprocess.run([str(site/'bin/openscrub'),'--help'],cwd=art,env=env,text=True,capture_output=True,check=True);assert 'usage:' in cli.stdout;(art/'installed-cli-help.txt').write_text(cli.stdout)
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
log=open(art/'installed-web.log','w');p=subprocess.Popen([str(site/'bin/openscrub-web'),'--http','--host','127.0.0.1','--port',str(port),'--retain-days','0'],cwd=art,env=env,stdout=log,stderr=subprocess.STDOUT)
try:
 for i in range(100):
  try:
   with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/jobs',timeout=1) as r:assert json.load(r)==[]
   break
  except OSError:assert p.poll() is None;time.sleep(.05)
 else:raise AssertionError('startup timeout')
 with urllib.request.urlopen(f'http://127.0.0.1:{port}/',timeout=2) as r:body=r.read().decode();assert 'OpenScrub' in body and 'function detChoices' in body and 'Keep visible' in body
finally:
 p.send_signal(signal.SIGTERM);p.wait(timeout=8);log.close()
assert p.returncode==0
result=dict(module_probe=info,installed_source_exact=True,default_options_unchanged=True,actual_cli_help=True,actual_web_entrypoint=True,homepage_and_jobs_api=True,idle_sigterm_exit=p.returncode)
(art/'installed-startup.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
