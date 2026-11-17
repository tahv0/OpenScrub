from pathlib import Path
import json,subprocess,os,signal,socket,time
r=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task9/fix1');records=[]
for line in subprocess.check_output(['ps','-C','python','-o','pid=,args='],text=True).splitlines():
 pid,args=line.strip().split(None,1)
 if args in ['python fix1/serve.py','python fix1/installed_smoke.py']:
  assert Path('/proc',pid,'cwd').resolve()==r.parent
  cmd=Path('/proc',pid,'cmdline').read_bytes().replace(b'\0',b' ').decode().strip();assert cmd==args,(cmd,args)
  records.append({'pid':int(pid),'args':args});os.kill(int(pid),signal.SIGTERM)
assert len(records)==2,records
closed=[]
for port in [18513,18514]:
 deadline=time.monotonic()+5
 while True:
  try:s=socket.create_connection(('127.0.0.1',port),timeout=.2);s.close()
  except OSError:closed.append(port);break
  assert time.monotonic()<deadline,port;time.sleep(.05)
result={'owned_processes':records,'closed_ports':closed};(r/'evidence/cleanup.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
