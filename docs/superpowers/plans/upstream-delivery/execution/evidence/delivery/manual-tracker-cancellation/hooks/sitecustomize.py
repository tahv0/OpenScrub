import os
from pathlib import Path
profile = Path(os.environ['OPENSCRUB_TASK110_PROFILE'])
profile.mkdir(parents=True, exist_ok=True)
original = os.path.expanduser

def expanduser(path):
    if path == '~':
        return str(profile)
    if isinstance(path, str) and path.startswith('~/'):
        return str(profile / path[2:])
    return original(path)

os.path.expanduser = expanduser
os.environ['OPENSCRUB_NO_AUTOFETCH'] = '1'
