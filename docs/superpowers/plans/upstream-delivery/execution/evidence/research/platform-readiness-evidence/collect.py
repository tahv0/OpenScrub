import datetime
import glob
import json
from pathlib import Path
import shutil
import subprocess

out = Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/platform-readiness-evidence')
checks = [
    ('docker-client', ['docker', '--version']),
    ('docker-buildx', ['docker', 'buildx', 'version']),
    ('docker-context', ['docker', 'context', 'show']),
    ('docker-info', ['docker', 'info', '--format', 'ServerVersion={{.ServerVersion}} OSType={{.OSType}} Architecture={{.Architecture}} OperatingSystem={{.OperatingSystem}} Runtimes={{json .Runtimes}}']),
    ('gpu-query', ['nvidia-smi', '--query-gpu=name,driver_version,memory.total', '--format=csv,noheader']),
    ('uname', ['uname', '-srm']),
]
rows = []
for name, command in checks:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        row = dict(name=name, command=command, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
    except (OSError, subprocess.TimeoutExpired) as error:
        row = dict(name=name, command=command, returncode=None, error=str(error))
    rows.append(row)
    print(json.dumps(row))
tools = ['docker', 'nvidia-smi', 'cmd.exe', 'powershell.exe', 'pwsh.exe', 'cl.exe', 'msbuild.exe', 'dotnet.exe', 'pyinstaller', 'wine', 'wine64']
metadata = dict(
    captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    tool_paths={tool: shutil.which(tool) for tool in tools},
    device_nodes={pattern: glob.glob(pattern) for pattern in ['/dev/dxg', '/dev/nvidia[0-9]*', '/dev/nvidiactl', '/dev/dri/renderD*']},
    os_release=Path('/etc/os-release').read_text(),
    checks=rows,
    limits='Read-only metadata and bounded daemon/GPU queries; no process/container/image inventory; no build or inference.',
)
(out / 'local-capability.json').write_text(json.dumps(metadata, indent=2) + '\n')
