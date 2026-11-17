import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

art=Path('/tmp/openscrub-task651')
site=art/'installed/site-packages'
(art/'installed-profile').mkdir(exist_ok=True)
profile=Path(tempfile.mkdtemp(prefix='run-',dir=art/'installed-profile'))
env=dict(os.environ, PYTHONPATH=str(art/'installed-hooks')+':'+str(site), OPENSCRUB_NO_AUTOFETCH='1', PYTHONDONTWRITEBYTECODE='1', OPENSCRUB_TASK651_PROFILE=str(profile))
python='/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python'
probe=subprocess.run([python,'-c','import openscrub, openscrub_web, openscrub_internal.lifetimes; print(openscrub.__file__); print(openscrub_web.JOBS_DIR)'],
    cwd=art,env=env,text=True,capture_output=True,check=True)
assert str(site) in probe.stdout and str(art/'installed-profile') in probe.stdout
probe_defaults=subprocess.run([python,'-c', '''import inspect, json, openscrub, openscrub_web as web; a=openscrub.build_parser().parse_args(['synthetic.avi']); b=web.build_args(dict(video='synthetic.avi', options={}, dir='/tmp/openscrub-task651/installed-defaults')); assert (a.engine,a.device,a.encoder,a.mode,a.pad,a.coverage,a.out_quality)==('auto','auto','auto','blur',8,'tight','archival'); assert (b.engine,b.device,b.encoder,b.mode,b.pad,b.coverage,b.out_quality)==('auto','auto','auto','blur',8,'tight','archival'); assert inspect.signature(openscrub.write_report).parameters['publisher'].default is None; print('installed CLI/web defaults and optional publisher: passed')'''],cwd=art,env=env,text=True,capture_output=True,check=True)
print(probe_defaults.stdout)
cli=subprocess.run([str(site/'bin/openscrub'),'--help'],cwd=art,env=env,text=True,capture_output=True,check=True)
assert 'usage:' in cli.stdout and 'video' in cli.stdout
(art/'installed-cli-help.txt').write_text(cli.stdout)
with socket.socket() as sock:
    sock.bind(('127.0.0.1',0))
    port=sock.getsockname()[1]
log=open(art/'installed-web.log','w')
process=subprocess.Popen([str(site/'bin/openscrub-web'),'--http','--host','127.0.0.1','--port',str(port),'--retain-days','0'],cwd=art,env=env,stdout=log,stderr=subprocess.STDOUT)
base='http://127.0.0.1:'+str(port)
def call(path, body=None):
    data=json.dumps(body).encode() if body is not None else None
    request=urllib.request.Request(base+path,data=data,headers={'Content-Type':'application/json'} if data else {})
    with urllib.request.urlopen(request,timeout=3) as response:
        content=response.read()
        return response.status,content
try:
    deadline=time.monotonic()+10
    while True:
        try:
            status,body=call('/api/jobs')
            break
        except (OSError,urllib.error.URLError):
            assert process.poll() is None, 'installed web exited before serving'
            if time.monotonic()>deadline:raise
            time.sleep(.05)
    assert status==200 and json.loads(body)==[]
    assert b'OpenScrub' in call('/')[1]
    assert json.loads(call('/api/allowlist',{'words':['synthetic-installed-name']})[1])['count']==1
    assert json.loads(call('/api/allowlist')[1])['words']==['synthetic-installed-name']
    assert call('/api/vault/setup',{'password':'synthetic-installed-password'})[0]==200
    assert not json.loads(call('/api/vault')[1])['locked']
    assert call('/api/vault/lock',{})[0]==200
    assert json.loads(call('/api/vault')[1])['locked']
    for body in [None, {'words':['late-name']}]:
        try:
            call('/api/allowlist',body)
        except urllib.error.HTTPError as error:
            assert error.code==423
            error.close()
        else:
            raise AssertionError('installed allowlist bypassed locked admission')
    assert call('/api/vault/unlock',{'password':'synthetic-installed-password'})[0]==200
    assert json.loads(call('/api/allowlist')[1])['words']==['synthetic-installed-name']
finally:
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
        raise AssertionError('installed shutdown did not finish')
    log.close()
assert process.returncode==0
result={'installed_module_probe':probe.stdout.splitlines(),'actual_cli_help':True,
    'actual_web_entrypoint_cheroot':True,'homepage_and_job_api':True,
    'real_vault_setup_lock_unlock':True,'allowlist_ready_locked_recovered':True,'idle_sigterm_exit':process.returncode,
    'runtime_data_root':str(profile),'no_model_fetches':True}
(art/'installed-startup.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
