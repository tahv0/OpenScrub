"""Source gate and explicit app configuration, usable by standalone scripts."""
import hashlib
import json
import os
from pathlib import Path
import sys
ROOT = Path('/home/tahv0/src/OpenScrub/.superpowers/sdd/README/runtime/task1202')
def configure():
    import openscrub
    import openscrub_web as web
    import zones_ui
    selected = Path(os.environ['TASK1202_SOURCE']).resolve()
    sources = {}
    for module in (openscrub, web, zones_ui):
        source = Path(module.__file__).resolve()
        assert source.parent == selected, (source, selected)
        sources[module.__name__] = {'file': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
    expected = os.environ.get('TASK1202_WEB_HASH')
    if expected:
        assert sources['openscrub_web']['sha256'] == expected
    openscrub._model_dir = lambda: str(ROOT / 'models')
    original_fetch = openscrub._fetch_model
    def offline(url, *args, **kwargs):
        if not url.startswith('file://'):
            raise RuntimeError('Task1202 model downloads disabled')
        return original_fetch(url, *args, **kwargs)
    openscrub._fetch_model = offline
    data = ROOT / 'app'
    data.mkdir(exist_ok=True)
    web._data_root = lambda: str(data)
    for name in ('JOBS_DIR', 'ZONES_PATH', 'MODEL_SELECT_PATH', 'CERT_DIR', 'WEB_SETTINGS_PATH', 'CUSTOM_CATS_PATH'):
        setattr(web, name, str(data / Path(getattr(web, name)).name))
    for name in ('CUSTOM_CERT', 'CUSTOM_KEY', 'AUTO_CERT', 'AUTO_KEY'):
        setattr(web, name, str(Path(web.CERT_DIR) / Path(getattr(web, name)).name))
    Path(web.JOBS_DIR).mkdir(exist_ok=True)
    print('TASK1202_ACTIVE_SOURCE ' + json.dumps({'python':sys.version,'sources':sources},sort_keys=True), flush=True)
    return web

def pytest_configure(config):
    configure()
