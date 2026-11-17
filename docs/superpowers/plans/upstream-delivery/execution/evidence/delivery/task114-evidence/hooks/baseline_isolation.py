"""Task-local baseline harness: isolate runtime data and forbid model fetches."""
from pathlib import Path
import os

ROOT = Path('/tmp/openscrub-task114')
BASE = ROOT / 'base'

def configure(data_name='app'):
    os.environ['OPENSCRUB_NO_AUTOFETCH'] = '1'
    import hashlib, importlib.util
    spec = importlib.util.find_spec('openscrub')
    expected = BASE / 'openscrub.py'
    assert Path(spec.origin).resolve() == expected
    assert hashlib.sha256(expected.read_bytes()).hexdigest() == '0e4f0f9a7846080f591038d021aaf3ca6f01201d83ac32bbdc273f53d5067ee7'
    import openscrub
    models = Path(os.environ.get('OPENSCRUB_BASELINE_MODEL_DIR', str(ROOT / 'synthetic-data' / 'models')))
    models.mkdir(parents=True, exist_ok=True)
    openscrub._model_dir = lambda: str(models)
    original_fetch = openscrub._fetch_model
    def local_only_fetch(url, *args, **kwargs):
        if not url.startswith('file://'):
            raise RuntimeError('Baseline policy: model network downloads disabled')
        return original_fetch(url, *args, **kwargs)
    openscrub._fetch_model = local_only_fetch
    web_spec = importlib.util.find_spec('openscrub_web')
    web_expected = BASE / 'openscrub_web.py'
    assert Path(web_spec.origin).resolve() == web_expected
    assert hashlib.sha256(web_expected.read_bytes()).hexdigest() == '9835e1137abee62c0a78e2669ed8bae7059e36bf4bed9f5c7a44f0eb8b40ed3a'
    import openscrub_web as web
    data = ROOT / 'synthetic-data' / data_name
    data.mkdir(parents=True, exist_ok=True)
    web._data_root = lambda: str(data)
    for name in ('JOBS_DIR', 'ZONES_PATH', 'MODEL_SELECT_PATH', 'CERT_DIR',
                 'WEB_SETTINGS_PATH', 'CUSTOM_CATS_PATH'):
        setattr(web, name, str(data / Path(getattr(web, name)).name))
    for name in ('CUSTOM_CERT', 'CUSTOM_KEY', 'AUTO_CERT', 'AUTO_KEY'):
        setattr(web, name, str(Path(web.CERT_DIR) / Path(getattr(web, name)).name))
    Path(web.JOBS_DIR).mkdir(parents=True, exist_ok=True)
    return web

def pytest_configure(config):
    configure()
