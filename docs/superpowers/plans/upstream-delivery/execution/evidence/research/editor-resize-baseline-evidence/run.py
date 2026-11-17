"""Own server/browser lifecycle. No product edits, installs, model or network use."""
import os,sys,subprocess,json,time,urllib.request,signal
from pathlib import Path
ROOT=Path('/tmp/openscrub-editor-resize-baseline-20261117')
env=os.environ.copy()
env.update({'OPENSCRUB_NO_AUTOFETCH':'1','PYTHONDONTWRITEBYTECODE':'1',
 'PLAYWRIGHT_BROWSERS_PATH':'/tmp/openscrub-save-as-20261116/browsers',
 'LD_LIBRARY_PATH':'/tmp/openscrub-save-as-20261116/tools/usr/lib/x86_64-linux-gnu:'+env.get('LD_LIBRARY_PATH','')})
versions=[('baseline','e21ebdf6e3ee46e6c65050dc956a9a3459152269',18561),('p07a','92124753736e287ac800af91f0ac96f3e96c01be',18562)]
processes=[]; logs=[]
try:
 for label,sha,port in versions:
  log=open(ROOT/(label+'-server.log'),'w');logs.append(log)
  p=subprocess.Popen([sys.executable,str(ROOT/'serve.py'),label,sha,str(port)],cwd=ROOT/label,env=env,stdout=log,stderr=subprocess.STDOUT);processes.append(p)
  for _ in range(150):
   if p.poll() is not None: raise RuntimeError(f'{label} server exited; see log')
   try:
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/jobs',timeout=.5) as r:
     if r.status==200:break
   except Exception:time.sleep(.1)
  else:raise TimeoutError(label)
 subprocess.run(['node',str(ROOT/'browser.cjs')],cwd=ROOT,env=env,check=True,timeout=150)
finally:
 for p in processes:
  if p.poll() is None:p.send_signal(signal.SIGINT)
 for p in processes:
  try:p.wait(timeout=10)
  except subprocess.TimeoutExpired:p.kill();p.wait()
 for f in logs:f.close()
 (ROOT/'cleanup.json').write_text(json.dumps({'servers':[{'pid':p.pid,'returncode':p.returncode} for p in processes],'all_reaped':all(p.poll() is not None for p in processes)},indent=2))
