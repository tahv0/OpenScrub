import hashlib
import json
from pathlib import Path
import subprocess

art = Path('/tmp/openscrub-task109')
root = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
provenance = json.loads((art / 'final-provenance.json').read_text())
head = 'ded411cbec308333d1416ae3d58b4f6e918d7849'
base = 'e21ebdf6e3ee46e6c65050dc956a9a3459152269'
assert Path.cwd() == root
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == head
assert subprocess.check_output(['git', 'rev-parse', 'HEAD^'], text=True).strip() == base
assert not subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()
manifest = json.loads((art / 'tested-source-sha256.json').read_text())
for name, expected in manifest.items():
    committed = subprocess.check_output(['git', 'show', head + ':' + name])
    assert (root / name).read_bytes() == committed, name
    assert hashlib.sha256(committed).hexdigest() == expected, name
assert provenance['head'] == head and provenance['base'] == base
subprocess.run(['git', 'diff', '--check', base, head], check=True)
print('PASS: exact base/head, clean native worktree, all 114 tested source hashes match committed bytes, diff check')
