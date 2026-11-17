from pathlib import Path
import hashlib,json,subprocess
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub');art=Path('/tmp/openscrub-task632')
paths=subprocess.check_output(['git','-C',str(root),'ls-files'],text=True).splitlines()+['tests/test_report_serialization.py']
manifest={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}
(art/'verification-source.json').write_text(json.dumps(manifest,indent=2))
print(len(manifest),'source blobs frozen')
