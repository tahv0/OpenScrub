import importlib.util,json,os,socket,subprocess,sys,time,urllib.request
from pathlib import Path
art=Path('/tmp/openscrub-task164');source=art/'installed/site-packages';tests=art/'sdist-extracted/openscrub-1.0.96/tests';out=art/'installed-browser';out.mkdir(exist_ok=True)
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
with (out/'server.log').open('w') as log:
 p=subprocess.Popen([sys.executable,str(tests/'editor_resize_server.py'),str(source),str(out/'runtime'),str(port)],cwd=source,stdout=log,stderr=subprocess.STDOUT)
 try:
  for _ in range(150):
   try:urllib.request.urlopen(f'http://127.0.0.1:{port}/api/jobs',timeout=.5).close();break
   except OSError:
    assert p.poll() is None;time.sleep(.1)
  else:raise TimeoutError('installed test server')
  result=subprocess.run(['node',str(tests/'editor_resize_browser.cjs'),f'http://127.0.0.1:{port}',str(out)],text=True,capture_output=True,timeout=180)
  (out/'browser.log').write_text(result.stdout+result.stderr);assert result.returncode==0,result.stdout+result.stderr
  spec=importlib.util.spec_from_file_location('packaged_resize_test',tests/'test_editor_resize.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.verify_render(out)
  identity=json.loads((out/'runtime/server-identity.json').read_text());assert Path(identity['web_import']).parent==source
  print('Exact packaged browser tests against installed-only product: DPR1+DPR2 real pixels/pointers/lifecycle/save/fresh reopen/SDR output passed')
 finally:
  p.terminate()
  try:p.wait(timeout=10)
  except subprocess.TimeoutExpired:p.kill();p.wait();raise
