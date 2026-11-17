import datetime, json, pathlib, platform, subprocess, sysconfig, sys
root=pathlib.Path('/tmp/openscrub-opencv-resolution-20261117')
code='''import json, platform, sys, sysconfig
from packaging.markers import default_environment
print(json.dumps({'executable':sys.executable,'version':sys.version,'version_info':list(sys.version_info),'platform':sysconfig.get_platform(),'abi':sysconfig.get_config_var('SOABI'),'libc':platform.libc_ver(),'marker_environment':default_environment()}))'''
targets={}
for key,path in [('312','/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python'),('39','/tmp/openscrub-python39-20261117/venv/bin/python')]:
    targets[key]=json.loads(subprocess.check_output([path,'-B','-c',code],env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1'},cwd=root))
(root/'targets.json').write_text(json.dumps(targets,indent=2)+'\n')
print(json.dumps(targets,indent=2))
