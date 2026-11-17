"""Final documentation-only checks; no product/benchmark rerun."""
from pathlib import Path
import hashlib,json,subprocess
art=Path('/tmp/openscrub-task632');docs=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README');root=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
for name in ('task-632-report.md','task-632-pr.md'):
 p=docs/name;s=p.read_text().replace('is**12,000,002 characters**,22 pieces','is **12,000,002 characters**, 22 pieces')
 p.write_text(s)
report=(docs/'task-632-report.md').read_text();pr=(docs/'task-632-pr.md').read_text()
evidence=json.loads((art/'committed-evidence.json').read_text());r=json.loads((art/'measurement/results.json').read_text())
assert evidence['base'] in report and evidence['head'] in report and evidence['head'] in pr
assert 'All 126 before and 127 after Git blobs' in report
assert len(r['sources']['before']['sha256'])==126 and len(r['sources']['after']['sha256'])==127
assert r['sources']['before']['sha256']['openscrub.py']==r['sources']['after']['sha256']['openscrub.py']
assert r['sources']['before']['sha256']['openscrub_web.py']==r['sources']['after']['sha256']['openscrub_web.py']
assert 'regresses 9.97%' in report and 'regresses 9.97%' in pr
assert '456 passed' in report and '159 passed' in report and '168 passed' in report
assert not subprocess.check_output(['git','-C',str(root),'status','--porcelain'])
subprocess.run(['git','-C',str(root),'diff','--check'],check=True)
manifest={}
for p in art.glob('*'):
 if p.is_file() and p.name!='handoff-manifest.json':manifest[str(p.relative_to(art))]=hashlib.sha256(p.read_bytes()).hexdigest()
for p in [art/'measurement/results.json',art/'count-smoke/results.json',*list((art/'dist').glob('*'))]:
 if p.is_file():manifest[str(p.relative_to(art))]=hashlib.sha256(p.read_bytes()).hexdigest()
for name in ('task-632-report.md','task-632-pr.md'):manifest[name]=hashlib.sha256((docs/name).read_bytes()).hexdigest()
(art/'handoff-manifest.json').write_text(json.dumps(manifest,indent=2))
print('Documentation and exact clean head verified:',evidence['head'])
print('Detailed report:',docs/'task-632-report.md')
print('PR draft:',docs/'task-632-pr.md')
print('Main evidence SHA256:',manifest['measurement/results.json'])
