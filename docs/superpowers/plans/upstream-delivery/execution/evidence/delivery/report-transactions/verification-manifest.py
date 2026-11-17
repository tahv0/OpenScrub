from pathlib import Path
import hashlib,json,platform,subprocess
import openscrub, cv2, numpy, cheroot, pytest, importlib.metadata
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
files=['openscrub.py','openscrub_web.py','openscrub_internal/lifetimes.py','tests/test_report_transactions.py']
result={'python':platform.python_version(),'versions':{n:importlib.metadata.version(n) for n in ['opencv-python','numpy','cheroot','pytest','build']},'source':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}}
Path('/tmp/openscrub-task622/verification-source.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
