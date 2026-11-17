from pathlib import Path
import tarfile,zipfile,hashlib,json
r=Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task9/fix1');source=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub');sdist=next((r/'dist').glob('*.tar.gz'));wheel=next((r/'dist').glob('*.whl'))
checks={}
with tarfile.open(sdist) as t:
 for name in ['openscrub.py','openscrub_web.py','zones_ui.py','openscrub_vault.py','tests/test_thumbnail_scheduling.py','tests/test_review_choices.py','tests/test_review_save_failures.py','test_openscrub.py']:
  assert t.extractfile('openscrub-1.0.96/'+name).read()==(source/name).read_bytes(),name;checks['sdist:'+name]='exact'
with zipfile.ZipFile(wheel) as z:
 for name in ['openscrub.py','openscrub_web.py','zones_ui.py','openscrub_vault.py','openscrub_setup.py','openscrub_update.py','face_models.json','plate_models.json','person_models.json']:
  assert z.read(name)==(source/name).read_bytes(),name;checks['wheel:'+name]='exact'
 metadata=z.read('openscrub-1.0.96.dist-info/METADATA').decode();assert 'Requires-Python: >=3.9' in metadata
 assert z.read('openscrub-1.0.96.dist-info/entry_points.txt').decode().count('openscrub-web = openscrub_web:main')==1
for p in (sdist,wheel):checks[p.name]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
(r/'evidence/package-check.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks,indent=2))
