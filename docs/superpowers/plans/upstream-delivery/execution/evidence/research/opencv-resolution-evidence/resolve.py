import datetime, json, os, pathlib, subprocess, sys, time
root=pathlib.Path('/tmp/openscrub-opencv-resolution-20261117')
uv='/tmp/openscrub-baseline-20261116/bootstrap/bin/uv'
targets={'312':'/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python','39':'/tmp/openscrub-python39-20261117/venv/bin/python'}
key=sys.argv[1]
mode=sys.argv[2] if len(sys.argv)>2 else 'online'
cache=root/('cache-'+key)
(root/'tmp').mkdir(exist_ok=True)
(cache).mkdir(exist_ok=True)
env={'PATH':'/usr/bin:/bin','TMPDIR':str(root/'tmp'),'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1','UV_PYTHON_DOWNLOADS':'never','UV_HTTP_TIMEOUT':'15','UV_HTTP_RETRIES':'0'}
cmd=[uv,'--no-config','--no-progress','--color','never','pip','compile',str(root/'core-candidate.in'),'--python',targets[key],'--no-python-downloads','--only-binary',':all:','--default-index','https://pypi.org/simple','--keyring-provider','disabled','--cache-dir',str(cache),'--no-strip-markers','--emit-index-annotation','--format','pylock.toml','--output-file',str(root/('pylock.'+key+'.toml')),'--verbose']
if mode=='offline':cmd+=['--offline']
meta={'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':cmd,'environment':env,'mode':mode,'target':targets[key]}
(root/('command-'+key+'-'+mode+'.json')).write_text(json.dumps(meta,indent=2)+'\n')
start=time.monotonic()
with (root/('resolver-'+key+'-'+mode+'.log')).open('w') as log:
    try:
        result=subprocess.run(cmd,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=100)
        meta['exit_code']=result.returncode
    except subprocess.TimeoutExpired:
        meta['timeout_seconds']=100
meta['duration_seconds']=time.monotonic()-start
meta['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
(root/('command-'+key+'-'+mode+'.json')).write_text(json.dumps(meta,indent=2)+'\n')
print(json.dumps(meta,indent=2))
print((root/('resolver-'+key+'-'+mode+'.log')).read_text()[-14000:])
