import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import cv2
import numpy as np
import openscrub

root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
art=Path('/tmp/openscrub-task162')
assert Path.cwd()==root
assert Path(openscrub.__file__).resolve()==root/'openscrub.py'
manifest=json.loads((art/'stable-source-sha256.json').read_text())
assert manifest==json.loads((art/'tested-source-sha256.json').read_text())
for name,digest in manifest.items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
base=ast.parse((art/'baseline-openscrub.py').read_text())
current=ast.parse((root/'openscrub.py').read_text())
base_defs={n.name:ast.dump(n) for n in base.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
current_defs={n.name:ast.dump(n) for n in current.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
for name,body in base_defs.items():
    if name not in ['blur_silhouette','_blur_silhouette_yuv10']:
        assert current_defs[name]==body,name
assert current_defs.keys()-base_defs.keys()=={'_silhouette_mask'}
site=art/'installed/site-packages'
for name in ['openscrub.py','openscrub_web.py','zones_ui.py','openscrub_setup.py','openscrub_update.py','openscrub_vault.py']:
    assert (site/name).read_bytes()==(root/name).read_bytes(),name
python='/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python'
for command in ['openscrub','openscrub-web']:
    assert (site/'bin'/command).read_text().splitlines()[0]=='#!'+python
result={'base':'e21ebdf6e3ee46e6c65050dc956a9a3459152269','head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
 'branch':subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
 'worktree':str(root),'python':sys.version,'opencv':cv2.__version__,'numpy':np.__version__,
 'ffmpeg':subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0],
 'status':subprocess.check_output(['git','status','--porcelain'],text=True),
 'engine_sha256':manifest['openscrub.py'],'test_sha256':manifest['tests/test_polygon_fallback.py'],
 'stable_files':len(manifest),'installed_source_byte_identity':True,'correct_runtime_entrypoint_shebangs':True,
 'unrelated_functions_and_defaults_ast_identical':True,
 'artifact_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (art/'dist').iterdir()}}
if result['head']!=result['base']:
    for name,digest in manifest.items():
        data=subprocess.check_output(['git','show','HEAD:'+name])
        assert hashlib.sha256(data).hexdigest()==digest,name
    assert result['status']==''
    result['committed_bytes_identical']=True
(art/'final-provenance.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
