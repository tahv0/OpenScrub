"""Read-only composed-source, archive and installed-byte audit; no product imports."""
import ast,hashlib,json,subprocess,tarfile,zipfile
from pathlib import Path
out=Path(__file__).resolve().parent.parent
cfg=json.loads((out/'package.json').read_text());repo=Path(cfg['source']);base=cfg['base'];head=cfg['head'];root=Path(cfg['scratch'])/'package312'
def sha(b):return hashlib.sha256(b).hexdigest()
def git(*a):return subprocess.check_output(['git','-C',str(repo),*a])
assert git('rev-parse','HEAD').decode().strip()==head
assert not git('status','--porcelain')
assert git('diff','--check')==b''
files=cfg['files']
for p,h in files.items():assert sha(git('show',head+':'+p))==sha((repo/p).read_bytes())==h
for p in files:
 if p.endswith('.py'):ast.parse((repo/p).read_text(),feature_version=(3,9))
package=json.loads((root/'package-identities.json').read_text())
with tarfile.open(package['sdist']['file']) as tf:
 names=tf.getnames();assert len(names)==len(set(names))
 for p in cfg['package']['sdist_files']:
  matched=[n for n in names if n.split('/',1)[-1]==p];assert len(matched)==1,(p,matched)
with zipfile.ZipFile(package['wheel']['file']) as z:
 mapping={p:p for p in cfg['package']['wheel_files']}
 mapping.update({'openscrub.ico':'assets/openscrub.ico','openscrub_THIRD_PARTY_NOTICES.md':'THIRD_PARTY_NOTICES.md'})
 installed={}
 for target,source in mapping.items():
  assert sha(z.read(target))==files[source]
  assert sha((root/'site-packages'/target).read_bytes())==files[source]
  installed[target]=files[source]
 metadata=z.read(next(p for p in z.namelist() if p.endswith('/METADATA'))).decode()
 assert 'Requires-Python: >=3.9' in metadata.splitlines()
 entrypoints=z.read(next(p for p in z.namelist() if p.endswith('/entry_points.txt'))).decode()
 assert 'openscrub = openscrub:main' in entrypoints and 'openscrub-web = openscrub_web:main' in entrypoints
 delta=git('diff','--name-only',base,head).decode().splitlines()
 assert set(delta)=={'openscrub.py','CONTRIBUTING.md','pyproject.toml','tests/test_hdr_decoder_cleanup.py','tests/test_render_resources.py'}
 report=dict(head=head,clean=True,diff_check='passed',python39_grammar='all declared Python members',sdist_member_count=len(names),sdist_unique_members=True,installed_bytes=installed,requires_python='>=3.9',changed_paths=delta,package=package)
(out/'final-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(head=head,clean=True,sdist_unique=True,installed_members=len(installed),python39_grammar=True,changed_paths=delta),sort_keys=True))
