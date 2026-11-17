import json
from pathlib import Path
import shutil

out = Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/platform-readiness-evidence')
paths = [
    '/sys/class/drm/renderD128/device/vendor',
    '/sys/class/drm/renderD128/device/device',
    '/mnt/c/Program Files (x86)/Inno Setup 6/ISCC.exe',
    '/mnt/c/Program Files/Inno Setup 6/ISCC.exe',
]
rows = []
for name in paths:
    path = Path(name)
    row = dict(path=name, exists=path.exists())
    if name.startswith('/sys/') and path.is_file():
        row['value'] = path.read_text().strip()
    rows.append(row)
result = dict(command='python3 /tmp/openscrub-platform-readiness-20261117/adapter-and-windows-paths.py', returncode=0, paths=rows, tool_paths={name: shutil.which(name) for name in ['python.exe', 'ISCC.exe']}, limits='Only exact numeric adapter vendor/device files and standard Inno Setup path existence; no serials, UUIDs or native program execution.')
(out / 'adapter-and-windows-paths.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
