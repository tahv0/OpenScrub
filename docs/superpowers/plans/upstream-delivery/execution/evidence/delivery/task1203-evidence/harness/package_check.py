"""Offline archive equality and the actual nested source updater."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import zipfile
ROOT=Path(os.environ['TASK1203_ROOT'])
SOURCE=Path(os.environ['TASK1203_SOURCE'])
sdist=next((ROOT/'dist').glob('*.tar.gz'))
wheel=next((ROOT/'wheel').glob('*.whl'))
required=['openscrub.py','openscrub_web.py','zones_ui.py','openscrub_internal/__init__.py','openscrub_internal/job_logs.py','tests/test_job_logs.py','tests/test_job_polling_node.py','tests/test_job_polling_browser.py','tests/test_browser_log_retention.py','test_openscrub.py','pyproject.toml','README.md','benchmark/browser_logs.py','benchmark/browser_logs.js','benchmark/browser_logs_env.py','benchmark/browser_logs_summary.py','benchmark/README.md']
records={}
with tarfile.open(sdist) as archive:
    members=archive.getmembers()
    prefix=members[0].name.split('/')[0]+'/'
    for path in required:
        data=archive.extractfile(prefix+path).read()
        assert data==(SOURCE/path).read_bytes(),path
        records[path]=hashlib.sha256(data).hexdigest()
with zipfile.ZipFile(wheel) as archive:
    for path in required[:5]:
        assert archive.read(path)==(SOURCE/path).read_bytes(),path
    metadata=archive.read(next(n for n in archive.namelist() if n.endswith('/METADATA'))).decode()
    assert 'Requires-Python: >=3.9' in metadata
# Run shipped source updater against the exact built sdist; no network.
import openscrub_update as updater
assert Path(updater.__file__).resolve().parent==SOURCE
update=ROOT/'updater-target'
update.mkdir(exist_ok=True)
updater.HERE=str(update)
blob=sdist.read_bytes()
updater.urllib.request.urlopen=lambda *_args,**_kwargs:io.BytesIO(blob)
notes=[]
updater.update_source({'sdist_url':'https://offline.invalid/sdist','sha256':hashlib.sha256(blob).hexdigest()},notes.append)
for path in required:
    assert (update/path).read_bytes()==(SOURCE/path).read_bytes(),path
record={'sdist':{'file':sdist.name,'bytes':sdist.stat().st_size,'sha256':hashlib.sha256(blob).hexdigest()},'wheel':{'file':wheel.name,'bytes':wheel.stat().st_size,'sha256':hashlib.sha256(wheel.read_bytes()).hexdigest()},'source_files':records,'updater':notes}
(ROOT/'package-identities.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
