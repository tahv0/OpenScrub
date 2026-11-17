import json,os,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parent
label,run_id=sys.argv[1:3]
args=sys.argv[3:]
command=['/usr/bin/python3','/home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py','--config',str(root/f'config-{label}.json'),'--run-id',run_id,'run','--','-m','pytest',*json.loads((root/'selection.json').read_text()),'-q',*args]
env=dict(os.environ)
for key in ['PYTHONPATH','PYTEST_PLUGINS','PYTEST_ADDOPTS','VERIFY_CONFIG','VERIFY_RUN']:
    env.pop(key,None)
(root/f'{run_id}-command.json').write_text(json.dumps(command,indent=2)+'\n')
with (root/f'{run_id}-controller.log').open('w') as stream:
    result=subprocess.run(command,env=env,stdout=stream,stderr=subprocess.STDOUT)
print('exit',result.returncode)
print('\n'.join((root/f'{run_id}-controller.log').read_text().splitlines()[-18:]))
sys.exit(result.returncode)
