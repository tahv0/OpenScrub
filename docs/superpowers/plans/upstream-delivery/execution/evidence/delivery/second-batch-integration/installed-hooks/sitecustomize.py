"""Keep installed entrypoints' writable profile within Task622 synthetic data."""
import os
from pathlib import Path
profile=Path(os.environ.get('OPENSCRUB_TASK651_PROFILE', '/tmp/openscrub-task651/installed-profile'))
profile.mkdir(parents=True,exist_ok=True)
original=os.path.expanduser

def expanduser(path):
    if path == '~':
        return str(profile)
    if isinstance(path,str) and path.startswith('~/'):
        return str(profile/path[2:])
    return original(path)
os.path.expanduser=expanduser
