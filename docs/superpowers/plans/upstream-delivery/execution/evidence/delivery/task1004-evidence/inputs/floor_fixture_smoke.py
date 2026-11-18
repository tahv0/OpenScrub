"""Actual Python 3.9 fixture import/start/listening HTTP; no browser replay."""
import importlib.util,json,os,socket,subprocess,sys,time,urllib.request
from pathlib import Path
assert sys.version_info[:2]==(3,9)
root=Path(os.environ['VERIFY_RUN']);cfg=json.loads(Path(os.environ['VERIFY_CONFIG']).read_text());source=Path(cfg['source'])
spec=importlib.util.spec_from_file_location('task1004_launcher',source/'tests/test_editor_resize.py')
launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
assert launcher.ROOT==source and callable(launcher.launch_editor_page)
with socket.socket() as sock:
 sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
runtime=root/'fixture-runtime';log=root/'logs'/'floor-server.log'
with log.open('w') as output:
 server=subprocess.Popen([sys.executable,'-B',str(source/'tests/editor_resize_server.py'),str(source),str(runtime),str(port)],cwd=source,stdout=output,stderr=subprocess.STDOUT)
 try:
  base='http://127.0.0.1:'+str(port)
  for _ in range(150):
   if server.poll() is not None:raise AssertionError(log.read_text())
   try:
    with urllib.request.urlopen(base+'/api/jobs',timeout=.5) as response:jobs=json.load(response)
    break
   except OSError:time.sleep(.1)
  else:raise AssertionError('actual3.9 fixture server did not listen')
  with urllib.request.urlopen(base+'/',timeout=10) as response:page=response.read().decode()
  with urllib.request.urlopen(base+'/api/jobs/cfr24/mediainfo',timeout=10) as response:media=json.load(response)
  with urllib.request.urlopen(base+'/api/jobs/cfr24/edit_sample?t=0.2',timeout=10) as response:sample=json.load(response)
  assert '<title>OpenScrub</title>' in page and 'function beReady(' in page
  assert media['duration']>0
  assert sample['version']==1 and sample['sample']['index']==4
  assert sample['sample']['canonical_s']==4/24 and sample['sample']['offset']==[8,-4]
  assert sample['sample']['policy']=='opencv-ffmpeg-zero-cfr-v1'
  assert [row['i'] for row in sample['boxes']]==[0,1] and sample['boxes'][1]['enabled'] is False
  identity=json.loads((runtime/'server-identity.json').read_text())
  assert identity['python'].startswith('3.9.25') and identity['web_import']==str(source/'openscrub_web.py')
  assert identity['engine_import']==str(source/'openscrub.py')
  assert identity['web_sha256']==cfg['files']['openscrub_web.py']
  record=dict(parent_python=sys.version,parent_executable=sys.executable,launcher_import=str(launcher.ROOT/'tests/test_editor_resize.py'),
   child_argv=[sys.executable,'-B',str(source/'tests/editor_resize_server.py'),str(source),str(runtime),str(port)],
   child_identity=identity,sample={key:sample[key] for key in ('version','sample','boxes')},page_bytes=len(page.encode()),browser_replay=False)
  (root/'logs/floor-fixture.json').write_text(json.dumps(record,indent=2)+'\n')
  print('ACTUAL_39_LAUNCHER_IMPORT_SERVER_HTTP_OK',json.dumps(record),flush=True)
 finally:
  server.terminate()
  try:server.wait(timeout=10)
  except subprocess.TimeoutExpired:server.kill();server.wait()
  assert server.poll() is not None
