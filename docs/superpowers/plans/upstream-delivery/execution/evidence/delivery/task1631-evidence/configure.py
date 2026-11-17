# Controller-only config generation: no application imports/execution.
import hashlib, json, pathlib, subprocess
root = pathlib.Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1631')
src = pathlib.Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
files = ['openscrub.py', 'openscrub_web.py', 'zones_ui.py', 'openscrub_update.py', 'openscrub_setup.py', 'openscrub_vault.py', 'pyproject.toml', 'test_openscrub.py']
files += [str(p.relative_to(src)) for p in (src / 'tests').glob('*.py')]
config = dict(task='task1631', scratch=str(root/'runs'), source=str(src), source_kind='git', base='e21ebdf6e3ee46e6c65050dc956a9a3459152269', head=subprocess.check_output(['git','-C',str(src),'rev-parse','HEAD'], text=True).strip(), policy='development', files={p:hashlib.sha256((src/p).read_bytes()).hexdigest() for p in files}, modules={p[:-3]:p for p in files if '/' not in p and p.endswith('.py') and not p.startswith('test_')}, python='/tmp/openscrub-baseline-20261116/venv-opencv4/bin/python', python_version=[3,12,16], min_free_bytes=2000000000, configure_app=True, prerequisites=[{'path':'/tmp/openscrub-baseline-20261116/tools/usr/bin/ffmpeg','executable':True}], environment={'LD_LIBRARY_PATH':'/tmp/openscrub-baseline-20261116/tools/usr/lib/x86_64-linux-gnu:/tmp/openscrub-baseline-20261116/tools/usr/lib/x86_64-linux-gnu/pulseaudio','TESSDATA_PREFIX':'/tmp/openscrub-baseline-20261116/tools/usr/share/tesseract-ocr/5/tessdata','PATH':'/tmp/openscrub-baseline-20261116/tools/usr/bin:/usr/bin:/bin'})
(root/'development.json').write_text(json.dumps(config,indent=2)+'\n')
