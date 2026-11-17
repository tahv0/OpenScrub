"""Task-only process isolation. No shell/user HOME or installed code changes."""
import os
from pathlib import Path
import sys

ROOT = Path('/tmp/openscrub-task652')
RUNTIME = ROOT / 'runtime'
(RUNTIME / 'profile').mkdir(parents=True, exist_ok=True)
_expanduser = os.path.expanduser

def _task_expanduser(path):
    marker = b'~' if isinstance(path, bytes) else '~'
    sep = b'/' if isinstance(path, bytes) else '/'
    if path == marker or path.startswith(marker + sep):
        base = os.fsencode(RUNTIME / 'profile') if isinstance(path, bytes) else str(RUNTIME / 'profile')
        return base + path[1:]
    return _expanduser(path)

os.path.expanduser = _task_expanduser
os.environ['OPENSCRUB_NO_AUTOFETCH'] = '1'

def _audit(event, args):
    if event == 'socket.connect':
        address = args[1]
        if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1', 'localhost'):
            raise RuntimeError('Python 3.9 verification: outward network disabled')
    if event == 'open':
        path, mode, flags = args
        if isinstance(path, (str, bytes)):
            write = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            resolved = Path(os.fsdecode(path)).resolve()
            if write and str(resolved) != os.devnull and not resolved.is_relative_to(ROOT):
                raise RuntimeError('Python 3.9 verification: write outside task root blocked')

sys.addaudithook(_audit)
