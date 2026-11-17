"""Caller-controlled config freeze from Git objects; no application execution."""
import hashlib, json, pathlib, subprocess
root=pathlib.Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1631')
config=json.loads((root/'development.json').read_text())
source=pathlib.Path(config['source'])
def git(*args): return subprocess.check_output(['git','-C',str(source),*args])
assert not git('status','--porcelain').strip()
head=git('rev-parse','HEAD').decode().strip()
config.update(head=head,policy='frozen')
paths=git('ls-tree','-r','--name-only',head).decode().splitlines()
config['files']={p:hashlib.sha256(git('show',head+':'+p)).hexdigest() for p in paths}
backend='/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1203/build-tools'
bootstrap='/tmp/openscrub-baseline-20261116/bootstrap/lib/python3.14/site-packages'
prereqs=[('/tmp/openscrub-baseline-20261116/tools/usr/bin/'+p,True) for p in ['ffmpeg','ffprobe','tesseract']]
prereqs += [(backend+'/hatchling/build.py',False), (bootstrap+'/pip/__main__.py',False),
('/tmp/openscrub-baseline-20261116/synthetic-data/models-opencv4/face_detection_yunet_2023mar.onnx',False),
(str(root/'listening_smoke.py'),False)]
config['prerequisites']=[dict(path=p,sha256=hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest(),executable=executable) for p,executable in prereqs]
config['package']=dict(tool_paths=[backend,bootstrap],sdist_files=['openscrub.py','openscrub_web.py','zones_ui.py','openscrub_update.py','openscrub_setup.py','openscrub_vault.py','pyproject.toml','test_openscrub.py','tests/test_render_geometry.py'],wheel_files=list(config['modules'].values()),requires_python='>=3.9',installed_commands=[['{target}/bin/openscrub','--help'],[str(root/'listening_smoke.py'),'{target}']])
(root/'frozen312.json').write_text(json.dumps(config,indent=2)+'\n')
config39=dict(config,python='/tmp/openscrub-python39-20261117/venv/bin/python',python_version=[3,9,25])
(root/'frozen39.json').write_text(json.dumps(config39,indent=2)+'\n')
print('FROZEN',head,len(config['files']))
