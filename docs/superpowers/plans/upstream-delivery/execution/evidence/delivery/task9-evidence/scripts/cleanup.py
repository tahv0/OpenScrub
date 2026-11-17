from pathlib import Path
import os,subprocess,json,urllib.request,socket,time,signal
r=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task9');result={'release':{},'processes':[],'ports_closed':[]}
for port in [18509,18510,18512]:
 req=urllib.request.Request(f'http://127.0.0.1:{port}/__qa__/control',json.dumps({'release_all':True,'save':True,'render':True}).encode(),{'Content-Type':'application/json'})
 with urllib.request.urlopen(req) as response:assert response.status==200
 with urllib.request.urlopen(f'http://127.0.0.1:{port}/__qa__/state') as response:state=json.load(response)
 assert not state['pending'] and not state['held'],state
 result['release'][port]={'pending':state['pending'],'held':state['held']}
for line in subprocess.check_output(['ps','-C','python','-o','pid=,args='],text=True).splitlines():
 pid,args=line.strip().split(None,1)
 if args.startswith('python '+str(r/'serve.py')) or args=='python installed_smoke.py':
  actual=Path('/proc')/pid/'cmdline';cmd=actual.read_bytes().replace(b'\0',b' ').decode().strip()
  assert str(r/'serve.py') in cmd or cmd=='python installed_smoke.py',cmd
  result['processes'].append({'pid':int(pid),'args':args});os.kill(int(pid),signal.SIGTERM)
for port in [18509,18510,18511,18512]:
 deadline=time.monotonic()+5
 while True:
  try:
   s=socket.create_connection(('127.0.0.1',port),timeout=.2);s.close()
  except OSError:result['ports_closed'].append(port);break
  assert time.monotonic()<deadline,port;time.sleep(.05)
(r/'evidence/cleanup.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
