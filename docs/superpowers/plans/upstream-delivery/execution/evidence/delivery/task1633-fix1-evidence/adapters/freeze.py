"""Task1633 I1 Git-pinned exports/configs; no product imports or dependency setup."""
import hashlib,io,json,subprocess,sys,tarfile,tomllib
from pathlib import Path
repo=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
sdd=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README')
root=sdd/'runtime/task1633/fix1'
base='64647f22e303af259f2cd7372fd1dc7c3be6e02a'
mode=sys.argv[1]
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args])
head=base if mode=='red' else git('rev-parse','HEAD').decode().strip()
source=root/('base-export' if mode=='red' else 'candidate-export')
assert not source.exists(),'exports are immutable; choose a new owned name for an observed revision'
source.mkdir()
with tarfile.open(fileobj=io.BytesIO(git('archive',head))) as archive:archive.extractall(source)
(source/'.verification-source.json').write_text(json.dumps(dict(head=head,base=base)))
tracked=git('ls-tree','-r','--name-only',head).decode().splitlines()
blob=lambda p:git('show',head+':'+p)
sha=lambda data:hashlib.sha256(data).hexdigest()
modules={p[:-3]:p for p in ['openscrub.py','openscrub_web.py','openscrub_setup.py','openscrub_update.py','openscrub_vault.py','zones_ui.py']}
for p in tracked:
 if p.startswith('openscrub_internal/') and p.endswith('.py'):
  modules[p[:-3].replace('/','.').removesuffix('.__init__')]=p
includes=tomllib.loads(blob('pyproject.toml').decode())['tool']['hatch']['build']['targets']['sdist']['include']
sdist=[p for p in tracked if p=='pyproject.toml' or any(p==i or p.startswith(i+'/') for i in includes)]
recipes=[p for p in tracked if p.startswith('Dockerfile') or p in ['docker/Dockerfile.opencv-cuda','windows/openscrub.spec']]
files={p:sha(blob(p)) for p in sorted(set(sdist+recipes))}
previous=json.loads((sdd/'task1633-evidence/package.json').read_text())
prereqs=[entry for entry in previous['prerequisites'] if '/execution/tooling/' in entry['path'] or entry['path'].startswith('/tmp/openscrub-baseline-20261116/tools/usr/bin/')]
for entry in prereqs:assert sha(Path(entry['path']).read_bytes())==entry['sha256']
adapter=sdd/'runtime/task1633/adapters/listening_publication.py'
for p in [Path(__file__),adapter]+[repo/'tests'/n for n in ['test_render_response_publication.py','test_job_lifecycle.py','test_report_transactions.py']]:prereqs.append(dict(path=str(p),sha256=sha(p.read_bytes())))
cfg=dict(task='task1633-fix1',scratch=str(sdd/'runtime/task1633/runs'),source=str(source),source_kind='export',base=base,head=head,policy='frozen',files=files,modules=modules,python=previous['python'],python_version=previous['python_version'],min_free_bytes=2000000000,configure_app=True,prerequisites=prereqs,environment=previous['environment'])
(root/'config'/('red.json' if mode=='red' else 'current.json')).write_text(json.dumps(cfg,indent=2)+'\n')
if mode!='red':
 floor=dict(cfg,python='/tmp/openscrub-python39-20261117/venv/bin/python',python_version=[3,9,25])
 (root/'config/python39.json').write_text(json.dumps(floor,indent=2)+'\n')
 package=dict(cfg)
 package['prerequisites']=prereqs+[entry for entry in previous['prerequisites'] if '/build-tools/' in entry['path'] or '/bootstrap/' in entry['path'] or '/build-wheelhouse/' in entry['path']]
 for entry in package['prerequisites']:assert sha(Path(entry['path']).read_bytes())==entry['sha256']
 package['package']=dict(tool_paths=previous['package']['tool_paths'],sdist_files=sdist,wheel_files=sorted(set(modules.values())|{'plate_models.json','face_models.json','person_models.json'}),requires_python='>=3.9',installed_commands=[['{target}/bin/openscrub','--help'],[str(adapter),'{target}']])
 package['excluded_paths']=['/home/tahv0/src/OpenScrub',str(repo)]
 (root/'config/package.json').write_text(json.dumps(package,indent=2)+'\n')
print(mode,base,head,len(files),'pins',len(modules),'modules',len(sdist),'sdist members')
