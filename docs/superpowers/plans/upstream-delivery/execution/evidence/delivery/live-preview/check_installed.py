import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

root = Path('/tmp/openscrub-task5')
site = root/'install/lib/python3.12/site-packages'
env = dict(os.environ, PYTHONPATH=str(site)+':'+str(root))
probe = subprocess.run([sys.executable, str(root/'verify_imports.py'), str(site)],
                       cwd=root,env=env,capture_output=True,text=True,check=True)
(root/'installed-imports.log').write_text(probe.stdout)
for executable in ('openscrub','openscrub-web'):
    result = subprocess.run([str(site/'bin'/executable),'--help'],cwd=root,env=env,
                            capture_output=True,text=True,check=True)
    assert 'usage:' in result.stdout
    (root/(executable+'-help.log')).write_text(result.stdout)
with socket.socket() as reservation:
    reservation.bind(('127.0.0.1',0))
    port = reservation.getsockname()[1]
log = (root/'installed-server.log').open('w')
command=[sys.executable,str(root/'run_installed_server.py'),'--http','--host','127.0.0.1',
         '--port',str(port),'--retain-days','0','--token','task5-synthetic-token']
process=subprocess.Popen(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
results=[]

def fetch(name,path,headers=None):
    lines=[f'GET {path} HTTP/1.1','Host: 127.0.0.1','Connection: close',
           'X-Token: task5-synthetic-token']
    lines += [f'{key}: {value}' for key,value in (headers or {}).items()]
    chunks=[]
    with socket.create_connection(('127.0.0.1',port),timeout=3) as conn:
        conn.sendall(('\r\n'.join(lines)+'\r\n\r\n').encode())
        while True:
            chunk=conn.recv(65536)
            if not chunk:break
            chunks.append(chunk)
    raw=b''.join(chunks)
    (root/(name+'.http')).write_bytes(raw)
    head,body=raw.split(b'\r\n\r\n',1)
    rows=head.decode('latin1').split('\r\n')
    status=int(rows[0].split()[1])
    actual=dict(row.split(': ',1) for row in rows[1:])
    results.append(dict(name=name,status=status,headers=actual,bytes=len(body),
                        sha256=hashlib.sha256(body).hexdigest()))
    return status,actual,body

try:
    deadline=time.monotonic()+10
    while True:
        try:
            assert fetch('installed-home','/')[0] == 200
            break
        except (OSError,IndexError):
            assert process.poll() is None, 'installed server exited early'
            if time.monotonic()>deadline:raise
            time.sleep(.05)
    expected=(root/'installed-expected.jpg').read_bytes()
    path='/api/jobs/installed-preview/preview.jpg'
    status,headers,body=fetch('installed-preview',path)
    assert status==200 and body==expected and int(headers['Content-Length'])==len(body)
    assert headers['Server']=='openscrub'
    assert headers['Content-Type']=='image/jpeg'
    assert headers['Content-Disposition']=='inline; filename=preview.jpg'
    assert headers['Cache-Control']=='no-cache, max-age=0'
    assert 'Last-Modified' not in headers
    assert fetch('installed-conditional',path,{'If-None-Match':headers['ETag']})[0]==304
    status,ranged,slice=fetch('installed-range',path,{'Range':'bytes=10-99','If-Range':headers['ETag']})
    assert status==206 and slice==expected[10:100] and ranged['Content-Length']=='90'
    assert fetch('installed-missing','/api/jobs/missing/preview.jpg')[0]==404
    process.send_signal(signal.SIGINT)
    assert process.wait(timeout=10)==0
    log.close()
    text=(root/'installed-server.log').read_text()
    assert str(site/'openscrub_web.py') in text and 'ENTRYPOINT' in text
    evidence=dict(command=command,imports=probe.stdout.splitlines(),results=results,
                  actual_cli_help=True,actual_web_help=True,actual_web_entrypoint=True,
                  actual_worker_startup=True,server_exit=process.returncode,
                  exact_preview_generation=True)
    (root/'installed-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print('installed imports, CLI/web help, actual web main/worker/Cheroot startup, exact JPEG/length, 304/206/404, SIGINT exit 0: passed')
finally:
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=10)
    log.close()
