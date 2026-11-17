import hashlib
import http.client
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path('/tmp/openscrub-task108')
name, import_root, port = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3])
runtime = ROOT/name
assert not runtime.exists()
env = dict(os.environ, PYTHONPATH=str(import_root)+':'+str(ROOT),
           TASK108_SERVER_NAME=name, TASK108_IMPORT_ROOT=str(import_root))
if 'site-packages' in str(import_root):
    env['TASK108_ENTRYPOINT'] = str(import_root/'bin/openscrub-web')
log = (ROOT/(name+'-server.log')).open('w')
command = [sys.executable, str(ROOT/'run_server.py'), '--http', '--host', '127.0.0.1',
           '--port', str(port), '--retain-days', '0', '--token', 'task108-synthetic-token']
process = subprocess.Popen(command, env=env, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
results = []

def request(method, path, body=None, headers=None):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
    connection.request(method, path, body=body, headers=headers or {'X-Token':'task108-synthetic-token'})
    response = connection.getresponse()
    data = response.read()
    item = {'method':method,'path':path,'status':response.status,'headers':dict(response.getheaders()),'body':data.decode()}
    connection.close()
    results.append(item)
    return response.status, data

try:
    deadline = time.monotonic()+10
    while True:
        try:
            assert request('GET','/api/jobs')[0] == 200
            break
        except (OSError, http.client.HTTPException):
            if process.poll() is not None or time.monotonic()>deadline:
                raise
            time.sleep(0.1)
    fixture = ROOT/'http-synthetic.avi'
    if not fixture.exists():
        import cv2
        import numpy as np
        writer = cv2.VideoWriter(str(fixture), cv2.VideoWriter_fourcc(*'MJPG'), 2.0, (64,48))
        assert writer.isOpened()
        for level in (40,100):
            writer.write(np.full((48,64,3), level, np.uint8))
        writer.release()
    source = fixture.read_bytes()
    for label, options in (('invalid','false'),('valid','{}')):
        boundary = 'task108-synthetic-boundary'
        body = ('--'+boundary+'\r\nContent-Disposition: form-data; name="options"\r\n\r\n'+options+
                '\r\n--'+boundary+'\r\nContent-Disposition: form-data; name="video"; filename="synthetic.avi"'+
                '\r\nContent-Type: video/x-msvideo\r\n\r\n').encode()+source+('\r\n--'+boundary+'--\r\n').encode()
        headers = {'X-Token':'task108-synthetic-token','Content-Type':'multipart/form-data; boundary='+boundary,'Content-Length':str(len(body))}
        raw = ('POST /api/jobs HTTP/1.1\r\nHost: 127.0.0.1:'+str(port)+'\r\n'+
               ''.join(k+': '+v+'\r\n' for k,v in headers.items())+'\r\n').encode()+body
        (ROOT/(name+'-'+label+'-request.http')).write_bytes(raw)
        status, response = request('POST','/api/jobs',body,headers)
        jobs_dir = runtime/'openscrub_jobs'
        if label == 'invalid':
            assert status == 400 and json.loads(response) == {'error':'Scan options must be a JSON object.'}
            assert list(jobs_dir.iterdir()) == []
            assert json.loads(request('GET','/api/jobs')[1]) == []
        else:
            assert status == 200
            jid, = json.loads(response)['jobs']
            assert (jobs_dir/jid/'options.json').read_bytes() == b'{}'
            assert hashlib.sha256((jobs_dir/jid/'input.avi').read_bytes()).digest() == hashlib.sha256(source).digest()
            assert request('POST','/api/jobs/'+jid+'/cancel')[0] == 200
            assert request('DELETE','/api/jobs/'+jid)[0] == 200
            assert json.loads(request('GET','/api/jobs')[1]) == []
            assert list(jobs_dir.iterdir()) == []
    # SIGINT takes the configured cheroot shutdown path and runs atexit.
    process.send_signal(signal.SIGINT)
    assert process.wait(timeout=10) == 0
    log.close()
    text = (ROOT/(name+'-server.log')).read_text()
    assert '"jobs": [], "queue": 0, "unfinished": 0' in text
    (ROOT/(name+'-http.json')).write_text(json.dumps({'command':command, 'results':results,
        'fixture_sha256':hashlib.sha256(source).hexdigest(),'cleanup':{'jobs':[], 'job_store_entries':[], 'queue':0,'unfinished':0,'server_exit':process.returncode}}, indent=2)+'\n')
    print(name, 'multipart false => JSON400, {} => 200; cancel/delete => 200; store/queue empty; server exit 0')
finally:
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=10)
    log.close()
