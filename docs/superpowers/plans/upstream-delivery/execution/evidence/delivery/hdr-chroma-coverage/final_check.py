import hashlib
import json
from pathlib import Path
import subprocess
import sys
import cv2
import numpy as np
import task161_isolation

task161_isolation.pytest_configure(None)
import openscrub
art=Path('/tmp/openscrub-task161')
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
base='e21ebdf6e3ee46e6c65050dc956a9a3459152269'
head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
assert subprocess.check_output(['git','rev-parse','HEAD^'],text=True).strip()==base
assert not subprocess.check_output(['git','status','--porcelain'],text=True).strip()
manifest=json.loads((art/'tested-source-sha256.json').read_text())
for name,digest in manifest.items():
    committed=subprocess.check_output(['git','show',head+':'+name])
    assert (root/name).read_bytes()==committed,name
    assert hashlib.sha256(committed).hexdigest()==digest,name
subprocess.run(['git','diff','--check',base,head],check=True)
result={'base':base,'head':head,'branch':subprocess.check_output(['git','branch','--show-current'],text=True).strip(),'native_worktree':str(root),'clean':True,'all_frozen_source_bytes_match_commit':True,'frozen_files':len(manifest),'python':sys.version,'executable':sys.executable,'opencv':cv2.__version__,'numpy':np.__version__,'ffmpeg':subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0],'engine_sha256':manifest['openscrub.py'],'test_sha256':manifest['tests/test_hdr_chroma_coverage.py']}
(art/'final-provenance.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
