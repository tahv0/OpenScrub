"""Freeze exact older-base source plus task recipes before each guarded run."""
from pathlib import Path
import hashlib,json,subprocess,sys
source=Path('/home/tahv0/.codex/worktrees/bde3/OpenScrub')
evidence=Path(__file__).parent
runtime=evidence.parent/'runtime/task150'
helper=evidence.parents[3]/'docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py'
helper=Path('/home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling/verify.py')
modules={n:n+'.py' for n in ['openscrub','openscrub_web','zones_ui','openscrub_vault','openscrub_update']}
files={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [*map(lambda n:source/n,modules.values()),source/'openscrub_setup.py',source/'test_openscrub.py',source/'pyproject.toml',*[source/n for n in ['README.md','LICENSE','NOTICE','THIRD_PARTY_NOTICES.md','requirements.txt','install.py','face_models.json','plate_models.json','person_models.json','assets/openscrub.ico']],*sorted((source/'tests').rglob('*'))] if p.is_file() and '__pycache__' not in str(p)}
base='/tmp/openscrub-baseline-20261116'
config=dict(task='task150',scratch=str(runtime/'runs'),source=str(source),source_kind='git',base='2ae3257b9752e2d976ff7a0d39955a13c133273a',head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),policy='development' if '--development' in sys.argv else 'frozen',files=files,modules=modules,python=base+'/venv-opencv4/bin/python',python_version=[3,12,16],min_free_bytes=4294967296,configure_app=True,prerequisites=[{'path':str(helper),'sha256':hashlib.sha256(helper.read_bytes()).hexdigest()}],environment={'PATH':base+'/venv-opencv4/bin:'+base+'/tools/usr/bin:/tmp/openscrub-save-as-20261116/node/bin:/usr/bin:/bin','LD_LIBRARY_PATH':base+'/tools/usr/lib/x86_64-linux-gnu:'+base+'/tools/usr/lib/x86_64-linux-gnu/pulseaudio:/tmp/openscrub-save-as-20261116/tools/usr/lib/x86_64-linux-gnu','TESSDATA_PREFIX':base+'/tools/usr/share/tesseract-ocr/5/tessdata','PLAYWRIGHT_BROWSERS_PATH':'/tmp/openscrub-save-as-20261116/browsers','OPENSCRUB_PLAYWRIGHT_MODULE':'/tmp/openscrub-save-as-20261116/node_modules/playwright'})
for p in sorted(evidence.glob('*')):
 if p.is_file() and p.suffix in ('.py','.cjs'):config['prerequisites'].append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
model=Path(base+'/synthetic-data/models-opencv4/face_detection_yunet_2023mar.onnx')
plugin=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/task1631-evidence/adapters/task1631_fixture.py')
for p in [model,plugin]:config['prerequisites'].append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
config['excluded_paths']=[str(source),'/home/tahv0/src/OpenScrub','/home/tahv0/.codex/worktrees/c832/OpenScrub']
config['package']={'tool_paths':['/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1203/build-tools',base+'/bootstrap/lib/python3.14/site-packages'],'sdist_files':list(files),'wheel_files':[n for n in files if n in list(modules.values())+['openscrub_setup.py','face_models.json','plate_models.json','person_models.json']],'requires_python':'>=3.9','installed_commands':[['{target}/bin/openscrub','--help'],['{target}/bin/openscrub-web','--help'],[str(evidence/'installed.py')]]}
(evidence/'development.json' if config['policy']=='development' else evidence/'frozen.json').write_text(json.dumps(config,indent=2)+'\n')

if config['policy']=='frozen':
 floor=dict(config,python='/tmp/openscrub-python39-20261117/venv/bin/python',python_version=[3,9,25])
 (evidence/'floor.json').write_text(json.dumps(floor,indent=2)+'\n')
