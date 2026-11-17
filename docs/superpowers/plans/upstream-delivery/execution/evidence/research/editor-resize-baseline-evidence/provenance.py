"""Verify the complete pinned exports byte-for-byte against git archive (read only)."""
import subprocess,tarfile,io,json,hashlib
from pathlib import Path
ROOT=Path('/tmp/openscrub-editor-resize-baseline-20261117')
repo='/home/tahv0/src/OpenScrub'
versions=[('baseline','e21ebdf6e3ee46e6c65050dc956a9a3459152269'),('p07a','92124753736e287ac800af91f0ac96f3e96c01be')]
records=[]
for label,sha in versions:
 raw=subprocess.check_output(['git','archive',sha],cwd=repo)
 with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
  files=[m for m in archive.getmembers() if m.isfile()]
  digest=hashlib.sha256()
  for m in files:
   expected=archive.extractfile(m).read();actual=(ROOT/label/m.name).read_bytes()
   assert actual==expected,m.name
   digest.update(m.name.encode()+b'\0'+hashlib.sha256(actual).digest())
  records.append({'label':label,'sha':sha,'tree':subprocess.check_output(['git','rev-parse',sha+'^{tree}'],cwd=repo,text=True).strip(),
   'export':str(ROOT/label),'export_method':'git archive SHA | tar -x -C EXPORT',
   'full_archive_file_count':len(files),'verified_all_archive_files':True,'ordered_export_digest':digest.hexdigest(),
   'web_sha256':hashlib.sha256((ROOT/label/'openscrub_web.py').read_bytes()).hexdigest()})
(ROOT/'source-provenance.json').write_text(json.dumps(records,indent=2))
print(json.dumps(records,indent=2))
