import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError,HTTPError
root=Path('/tmp/openscrub-task4')
runner=str(root/'installed_entry.py')
for entry in ['openscrub','openscrub-web']:
    result=subprocess.run([sys.executable,runner,entry,'--help'],capture_output=True,text=True,check=True)
    assert 'usage:' in result.stdout
    (root/(entry+'-help.log')).write_text(result.stdout)
    print(entry,'--help -> 0, installed imports confirmed')
with socket.socket() as sock:
    sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
base=f'http://127.0.0.1:{port}'
with (root/'installed-server.log').open('w') as output:
    process=subprocess.Popen([sys.executable,runner,'openscrub-web','--host','127.0.0.1','--port',str(port),'--http','--retain-days','0'],stdout=output,stderr=subprocess.STDOUT)
    try:
        for _ in range(100):
            try:
                with urlopen(base+'/',timeout=2) as response:
                    assert response.status==200
                    page=response.read().decode()
                    assert '<title>OpenScrub</title>' in page
                    assert "stage's recent processing rate" in page
                    assert 'no-store' in response.headers.get('Cache-Control','')
                    break
            except URLError:
                assert process.poll() is None,'server stopped'
                time.sleep(.1)
        else: raise AssertionError('server not ready')
        print('GET / -> 200, installed emitted UI, no-store')
        for route in ['/api/jobs','/api/models/face','/api/model_status','/api/vault']:
            with urlopen(base+route,timeout=10) as response:
                payload=json.load(response)
                assert response.status==200
                if route=='/api/jobs':assert payload==[]
                print('GET',route,'-> 200 JSON',type(payload).__name__)
    finally:
        process.terminate();process.wait(timeout=15)
        print('Installed web shutdown:',process.returncode)
