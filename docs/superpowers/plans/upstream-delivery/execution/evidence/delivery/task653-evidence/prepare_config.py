import hashlib,json,subprocess
from pathlib import Path
root=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README')
src=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
evidence=root/'task653-evidence'
base='4b9bd7e576a8ae30369672b4b4722fc9752e233f'
head='117e41ac5ee857a6b367caf6ccbd479d78989ff2'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=src,text=True).strip()==head
assert not subprocess.check_output(['git','status','--porcelain'],cwd=src,text=True)
subprocess.run(['git','merge-base','--is-ancestor',base,head],cwd=src,check=True)
paths=subprocess.check_output(['git','ls-tree','-r','--name-only',head],cwd=src,text=True).splitlines()
selected=[p for p in paths if p.endswith(('.py','.json','.toml')) or p in ['benchmark/README.md','CONTRIBUTING.md','Dockerfile','Dockerfile.cpu','Dockerfile.gpu']]
files={p:hashlib.sha256(subprocess.check_output(['git','show',head+':'+p],cwd=src)).hexdigest() for p in selected}
modules={p[:-3].replace('/','.') if not p.endswith('/__init__.py') else p[:-12].replace('/','.') :p for p in selected if (p.startswith('openscrub_internal/') or p in ['openscrub.py','openscrub_web.py','openscrub_vault.py','openscrub_update.py','openscrub_setup.py','zones_ui.py'])}
prereq=[]
for p in ['/tmp/openscrub-baseline-20261116/tools/usr/bin/ffmpeg','/tmp/openscrub-baseline-20261116/tools/usr/bin/ffprobe','/tmp/openscrub-baseline-20261116/tools/usr/bin/tesseract']:
    prereq.append(dict(path=p,sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest(),executable=True))
common=dict(task='task653',scratch=str(root/'runtime/task653/runs'),source=str(src),source_kind='git',base=base,head=head,policy='frozen',files=files,modules=modules,min_free_bytes=2000000000,configure_app=True,prerequisites=prereq,environment=dict(PATH='/tmp/openscrub-baseline-20261116/tools/usr/bin:/usr/bin:/bin',LD_LIBRARY_PATH='/tmp/openscrub-baseline-20261116/tools/usr/lib/x86_64-linux-gnu:/tmp/openscrub-baseline-20261116/tools/usr/lib/x86_64-linux-gnu/pulseaudio',TESSDATA_PREFIX='/tmp/openscrub-baseline-20261116/tools/usr/share/tesseract-ocr/5/tessdata'))
for label,py,version in [('312','/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python',[3,12,16]),('39','/tmp/openscrub-python39-20261117/venv/bin/python',[3,9,25])]:
    cfg=dict(common,python=py,python_version=version)
    (evidence/f'config-{label}.json').write_text(json.dumps(cfg,indent=2)+'\n')
selection=['tests/test_tail_history_index.py','tests/test_reverse_recall_index.py','tests/test_first_scan_sanity.py','tests/test_dense_smoothing_io.py','tests/test_manual_tracker_cancel.py','tests/test_batch_integration.py','test_openscrub.py::test_track_person_size_jump_handoff']
(evidence/'selection.json').write_text(json.dumps([str(src/p) for p in selection],indent=2)+'\n')
(evidence/'frozen-identities.json').write_text(json.dumps(dict(base=base,head=head,files=files,modules=modules),indent=2)+'\n')
helpers=Path('/home/tahv0/src/OpenScrub/docs/superpowers/plans/upstream-delivery/execution/tooling')
(evidence/'helper-identities.json').write_text(json.dumps({str(helpers/p):hashlib.sha256((helpers/p).read_bytes()).hexdigest() for p in ['README.md','verify.py','verification_hook.py','sitecustomize.py']},indent=2)+'\n')
print(json.dumps(dict(head=head,modules=modules,declared_files=len(files),selection=selection),indent=2))
