from pathlib import Path
import hashlib,json,shutil,subprocess,tarfile,io
native=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub');art=Path('/tmp/openscrub-task164');out=art/'final-red-source'
out.mkdir(exist_ok=True)
archive=subprocess.check_output(['git','-C',str(native),'archive','92124753736e287ac800af91f0ac96f3e96c01be'])
with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(out,filter='data')
for p in (native/'tests').iterdir():
 if p.is_file():shutil.copy2(p,out/'tests'/p.name)
s=(art/'task164_isolation.py').read_text().replace("ROOT = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')", "ROOT = Path('/tmp/openscrub-task164/final-red-source')").replace("ART = Path('/tmp/openscrub-task164')", "ART = Path('/tmp/openscrub-task164/final-red')")
(art/'task164red_isolation.py').write_text(s)
result={'base':'92124753736e287ac800af91f0ac96f3e96c01be','web_sha256':hashlib.sha256((out/'openscrub_web.py').read_bytes()).hexdigest(),'test_files':{str(p.relative_to(native)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (native/'tests').iterdir() if p.is_file()}}
(art/'final-red-binding.json').write_text(json.dumps(result,indent=2))
