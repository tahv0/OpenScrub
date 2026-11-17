from pathlib import Path
import hashlib,json,subprocess
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
art=Path('/tmp/openscrub-task72')
files=sorted(set(subprocess.check_output(['git','-C',str(root),'ls-files'],text=True).splitlines()+['tests/test_manual_addition_replay.py']))
files=[n for n in files if n.endswith('.py') or n in ['pyproject.toml','requirements.txt']]
manifest={'base':'f2cdf4813c86296644911f3f0b09bfc56d3e03c5','source_root':str(root),'files':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in files}}
(art/'verification-source.json').write_text(json.dumps(manifest,indent=2))
print('Frozen source/test manifest:',len(files),'files')
