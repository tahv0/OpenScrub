"""Task1633 frozen Git export/config; never imports product code."""
import hashlib,json,subprocess,tarfile,io,sys
from pathlib import Path
repo=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
root=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1633')
base='8768e86dc1cd57720fd1c22eb6b539ae6bda6cde'
mode=sys.argv[1]; head=base if mode=='red' else subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD']).decode().strip()
source=root/('base-export' if mode=='red' else 'candidate-export')
if source.exists():
 import shutil
 shutil.rmtree(source)
source.mkdir()
data=subprocess.check_output(['git','-C',str(repo),'archive',head])
with tarfile.open(fileobj=io.BytesIO(data)) as tf: tf.extractall(source)
(source/'.verification-source.json').write_text(json.dumps(dict(base=base,head=head)))
paths=subprocess.check_output(['git','-C',str(repo),'ls-tree','-r','--name-only',head]).decode().splitlines()
modules={p[:-3]:p for p in ['openscrub.py','openscrub_web.py','openscrub_setup.py','openscrub_update.py','openscrub_vault.py','zones_ui.py']}
for p in paths:
 if p.startswith('openscrub_internal/') and p.endswith('.py'):
  modules[p[:-3].replace('/','.').removesuffix('.__init__')]=p
files={p:hashlib.sha256((source/p).read_bytes()).hexdigest() for p in paths if p.endswith('.py') or p.startswith('Dockerfile') or p in ['pyproject.toml','requirements.txt','CONTRIBUTING.md']}
old=json.loads(Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/task16330-evidence/frozen312.json').read_text())
prereqs=[v for v in old['prerequisites'] if 'task16330' not in v['path']]
for p in [Path(__file__)]+[repo/'tests'/n for n in ['test_render_publication.py','test_render_response_publication.py'] if (repo/'tests'/n).exists()]: prereqs.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
cfg=dict(task='task1633',scratch=str(root/'runs'),source=str(source),source_kind='export',base=base,head=head,policy='frozen',files=files,modules=modules,python=old['python'],python_version=old['python_version'],min_free_bytes=2000000000,configure_app=True,prerequisites=prereqs,environment=dict(old['environment'],PIP_NO_CACHE_DIR='1'))
(root/'config'/('red.json' if mode=='red' else 'current.json')).write_text(json.dumps(cfg,indent=2)+'\n')
print(mode,head,len(files),'files',len(modules),'modules')
