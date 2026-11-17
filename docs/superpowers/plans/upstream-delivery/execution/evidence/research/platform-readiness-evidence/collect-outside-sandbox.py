import datetime
import glob
import json
from pathlib import Path
import shutil
import subprocess

out = Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/platform-readiness-evidence')
checks = [
    ('docker-info', ['docker', 'info', '--format', 'ServerVersion={{.ServerVersion}} OSType={{.OSType}} Architecture={{.Architecture}} OperatingSystem={{.OperatingSystem}} RuntimeNames={{range $key, $value := .Runtimes}}{{$key}} {{end}}']),
    ('gpu-query', ['nvidia-smi', '--query-gpu=name,driver_version,memory.total', '--format=csv,noheader']),
]
rows = []
for name, command in checks:
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    rows.append(dict(name=name, command=command, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr))
paths = ['/dev/dxg', '/dev/nvidiactl', '/mnt/c/Windows/System32/cmd.exe', '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', '/mnt/c/Program Files/Microsoft Visual Studio/Installer/vswhere.exe', '/proc/sys/fs/binfmt_misc/WSLInterop']
metadata = dict(
    captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    execution='Authorized require_escalated bounded read-only queries; no sudo, OS permission or daemon changes.',
    tool_paths={tool: shutil.which(tool) for tool in ['cmd.exe', 'powershell.exe', 'pwsh.exe', 'cl.exe', 'msbuild.exe', 'dotnet.exe', 'pyinstaller', 'wine', 'wine64']},
    exact_path_exists={path: Path(path).exists() for path in paths},
    gpu_device_nodes={pattern: glob.glob(pattern) for pattern in ['/dev/dxg', '/dev/nvidia[0-9]*', '/dev/nvidiactl', '/dev/dri/renderD*']},
    checks=rows,
    limits='No native Windows programs invoked. PATH and exact standard location absence do not prove no tools exist anywhere on the Windows host. No hardware serial/UUID or running workload inventory.',
)
(out / 'outside-sandbox-capability.json').write_text(json.dumps(metadata, indent=2) + '\n')
print(json.dumps(metadata, indent=2))
