from pathlib import Path
import hashlib,json,subprocess
root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
files=sorted(set(subprocess.check_output(['git','-C',str(root),'ls-files'],text=True).splitlines()+['tests/test_batch_integration.py']))
files=[n for n in files if n.endswith('.py') or n in ['pyproject.toml','requirements.txt','README.md','CONTRIBUTING.md']]
Path('/tmp/openscrub-task650/verification-source.json').write_text(json.dumps({'base':'12919c96c6f7558136b50d7b4d85e5e6b62f1971','source_root':str(root),'files':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in files}},indent=2))
print('Frozen',len(files),'source/test/metadata files')
