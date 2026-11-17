"""Pytest and smoke isolation, analogous to the existing 3.12 harness."""
from pathlib import Path
import os

ROOT = Path('/tmp/openscrub-task632')

def configure(data_name='app'):
    os.environ['OPENSCRUB_NO_AUTOFETCH'] = '1'
    import openscrub
    models = ROOT / 'runtime' / 'models'
    models.mkdir(parents=True, exist_ok=True)
    openscrub._model_dir = lambda: str(models)
    original_fetch = openscrub._fetch_model
    def local_only_fetch(url, *args, **kwargs):
        if not url.startswith('file://'):
            raise RuntimeError('Python 3.9 verification: model downloads disabled')
        return original_fetch(url, *args, **kwargs)
    openscrub._fetch_model = local_only_fetch
    import openscrub_web as web
    data = ROOT / 'runtime' / data_name
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
