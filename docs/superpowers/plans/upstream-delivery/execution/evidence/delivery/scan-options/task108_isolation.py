"""Task-local runtime isolation; preserve installed baseline tools read-only."""
from pathlib import Path
import os
import shutil

ROOT = Path('/tmp/openscrub-task108')

def configure(name='suite'):
    os.environ['OPENSCRUB_NO_AUTOFETCH'] = '1'
    import openscrub
    models = ROOT / 'models'
    models.mkdir(exist_ok=True)
    existing = Path('/tmp/openscrub-baseline-20261116/synthetic-data/models-opencv4/face_detection_yunet_2023mar.onnx')
    model = models / existing.name
    if not model.exists():
        shutil.copyfile(existing, model)
    openscrub._model_dir = lambda: str(models)
    original_fetch = openscrub._fetch_model
    def local_only_fetch(url, *args, **kwargs):
        if not url.startswith('file://'):
            raise RuntimeError('Task108: model network downloads disabled')
        return original_fetch(url, *args, **kwargs)
    openscrub._fetch_model = local_only_fetch
    import openscrub_web as web
    data = ROOT / name
    data.mkdir(exist_ok=True)
    web._data_root = lambda: str(data)
    for key in ('JOBS_DIR', 'ZONES_PATH', 'MODEL_SELECT_PATH', 'CERT_DIR',
                'WEB_SETTINGS_PATH', 'CUSTOM_CATS_PATH'):
        setattr(web, key, str(data / Path(getattr(web, key)).name))
    for key in ('CUSTOM_CERT', 'CUSTOM_KEY', 'AUTO_CERT', 'AUTO_KEY'):
        setattr(web, key, str(Path(web.CERT_DIR) / Path(getattr(web, key)).name))
    Path(web.JOBS_DIR).mkdir(exist_ok=True)
    return web

def pytest_configure(config):
    configure()
