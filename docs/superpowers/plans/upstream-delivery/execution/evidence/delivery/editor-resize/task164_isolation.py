"""Task-local runtime roots, no model fetching, and actual native source gate."""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
ART = Path('/tmp/openscrub-task164')

def pytest_configure(config):
    assert Path.cwd() == ROOT, Path.cwd()
    import openscrub
    import openscrub_web as web
    import zones_ui
    sources = {}
    for module in (openscrub, web, zones_ui):
        source = Path(module.__file__).resolve()
        assert source.parent == ROOT, source
        sources[module.__name__] = {'file': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
    for name in ('run_render', 'render_hdr'):
        assert Path(getattr(openscrub, name).__code__.co_filename).resolve() == ROOT / 'openscrub.py'
    os.environ['OPENSCRUB_NO_AUTOFETCH'] = '1'
    openscrub._model_dir = lambda: str(ART / 'runtime/models')
    original_fetch = openscrub._fetch_model
    def local_only_fetch(url, *args, **kwargs):
        if not url.startswith('file://'):
            raise RuntimeError('Task164: model downloads disabled')
        return original_fetch(url, *args, **kwargs)
    openscrub._fetch_model = local_only_fetch
    data = ART / 'runtime/app'
    data.mkdir(parents=True, exist_ok=True)
    web._data_root = lambda: str(data)
    for name in ('JOBS_DIR', 'ZONES_PATH', 'MODEL_SELECT_PATH', 'CERT_DIR', 'WEB_SETTINGS_PATH', 'CUSTOM_CATS_PATH'):
        setattr(web, name, str(data / Path(getattr(web, name)).name))
    for name in ('CUSTOM_CERT', 'CUSTOM_KEY', 'AUTO_CERT', 'AUTO_KEY'):
        setattr(web, name, str(Path(web.CERT_DIR) / Path(getattr(web, name)).name))
    Path(web.JOBS_DIR).mkdir(parents=True, exist_ok=True)
    print('TASK164_ACTIVE_SOURCE ' + json.dumps({'python': sys.version, 'sources': sources}, sort_keys=True))
