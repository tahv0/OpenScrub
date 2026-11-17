"""Task1202 standalone and pytest write/network guard; installed source filter."""
import os
from pathlib import Path
import sys
ROOT = Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1203/fix1')
PROFILE = ROOT / 'profile'
PROFILE.mkdir(exist_ok=True)
_original = os.path.expanduser
def expanduser(path):
    marker = b'~' if isinstance(path, bytes) else '~'
    sep = b'/' if isinstance(path, bytes) else '/'
    if path == marker or path.startswith(marker + sep):
        return (os.fsencode(PROFILE) if isinstance(path, bytes) else str(PROFILE)) + path[1:]
    return _original(path)
os.path.expanduser = expanduser
os.environ['OPENSCRUB_NO_AUTOFETCH'] = '1'
if os.environ.get('TASK1203_INSTALLED'):
    source = Path(os.environ['TASK1203_SOURCE']).resolve()
    sys.path[:] = [p for p in sys.path if p and (Path(p).resolve() == source or not any(x in str(Path(p).resolve()) for x in ('/worktrees/', '/src/OpenScrub')) or Path(p).resolve().is_relative_to(ROOT))]
def audit(event, args):
    if event == 'socket.connect':
        address = args[1]
        if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1', 'localhost'):
            raise RuntimeError('Task1202 outward network disabled')
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path, mode, flags = args
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            resolved = Path(os.fsdecode(path)).resolve()
            if str(resolved) != os.devnull and not resolved.is_relative_to(ROOT):
                raise RuntimeError('Task1202 write outside runtime root: ' + str(resolved))
sys.addaudithook(audit)
