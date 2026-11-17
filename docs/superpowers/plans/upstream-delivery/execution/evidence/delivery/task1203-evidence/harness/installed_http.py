"""Launch installed actual web main and query the listening HTTP server."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
ROOT=Path(os.environ['TASK1203_ROOT'])
with socket.socket() as listener:
    listener.bind(('127.0.0.1',0))
    port=listener.getsockname()[1]
base='http://127.0.0.1:'+str(port)
with (ROOT/'logs/installed-startup.log').open('w') as output:
    proc=subprocess.Popen([sys.executable,str(ROOT/'installed_entry.py'),'web','--http','--host','127.0.0.1','--port',str(port),'--retain-days','0'],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(base+'/api/jobs',timeout=3) as response:
                    jobs=json.load(response)
                break
            except urllib.error.URLError:
                assert proc.poll() is None,'installed server exited'
                time.sleep(.1)
        else:
            raise AssertionError('installed readiness deadline')
        assert len(jobs)==1
        job=jobs[0]
        assert (job['log_len'],job['log_base'],job['log_retained'])==(2100,100,2000)
        with urllib.request.urlopen(base+'/api/jobs/'+job['id']+'/log?from=0',timeout=5) as response:
            snapshot=json.load(response)
        assert snapshot['reset']=='stale' and snapshot['lines'][0]=='installed-100'
        assert snapshot['len']==2100 and len(snapshot['lines'])==2000
        with urllib.request.urlopen(base+'/',timeout=5) as response:
            page=response.read().decode()
            assert 'no-store' in response.headers.get('Cache-Control','')
            assert 'logStatus' in page
        with urllib.request.urlopen(base+'/api/jobs/'+job['id']+'/log?from=2100&epoch=old',timeout=5) as response:
            assert json.load(response)['reset']=='epoch'
        try:
            urllib.request.urlopen(base+'/api/jobs/'+job['id']+'/log?from=garbage',timeout=5)
            raise AssertionError('missing400')
        except urllib.error.HTTPError as error:
            assert error.code==400
        browser = subprocess.run(['node', str(ROOT/'installed_browser.js')],
                                 env=dict(os.environ, INSTALLED_BASE=base, INSTALLED_JOB=job['id']),
                                 capture_output=True, text=True, timeout=90)
        (ROOT/'logs/installed-browser.log').write_text(browser.stdout+browser.stderr)
        assert browser.returncode == 0, browser.stdout+browser.stderr
        print(browser.stdout, end='')
        print(json.dumps({'base':base,'metadata':'200 absolute2100/base100/count2000','log':'200 stale/epoch','malformed':'400','page':'200 no-store','server':'actual installed openscrub-web main/cheroot'},sort_keys=True))
    finally:
        proc.terminate()
        proc.wait(timeout=15)
        print('installed server exit',proc.returncode)
