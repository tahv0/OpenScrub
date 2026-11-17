"""Focused production FaceDetector probe; no downloads or user/cache accesses."""
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import traceback

ROOT = Path('/tmp/openscrub-opencv-compat-20261117')
SOURCE = ROOT / 'source' / 'openscrub.py'
CACHE = Path('/tmp/openscrub-baseline-20261116/synthetic-data/models-opencv4')
MODEL = CACHE / 'face_detection_yunet_2023mar.onnx'
PIN = '8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4'
assert hashlib.sha256(MODEL.read_bytes()).hexdigest() == PIN
os.environ['OPENSCRUB_NO_AUTOFETCH'] = '1'
os.environ.pop('OPENSCRUB_FACE_MODEL', None)
network_events = []

def audit(event, args):
    if event in ('socket.connect', 'socket.connect_ex', 'socket.getaddrinfo'):
        network_events.append(event)
        raise RuntimeError('Probe policy: network disabled')

sys.addaudithook(audit)
spec = importlib.util.spec_from_file_location('openscrub_probe', SOURCE)
app = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = app
spec.loader.exec_module(app)
cv2, np = app.cv2, app.np
fetch_attempts = []

def no_fetch(url, dest, *args, **kwargs):
    fetch_attempts.append({'url': url, 'dest': str(dest)})
    raise RuntimeError('Probe policy: model downloads disabled')

app._fetch_model = no_fetch
packages = {}
for name in ('opencv-python', 'opencv-python-headless', 'opencv-contrib-python',
             'opencv-contrib-python-headless', 'numpy'):
    try:
        dist = importlib.metadata.distribution(name)
        packages[name] = {'version': dist.version,
                          'requires_python': dist.metadata.get('Requires-Python')}
    except importlib.metadata.PackageNotFoundError:
        pass

namespaces = {}
for name in ('objdetect', 'xobjdetect', 'legacy', 'dnn'):
    namespace = getattr(cv2, name, None)
    namespaces[name] = None if namespace is None else [
        n for n in dir(namespace) if any(t in n.lower() for t in
                                        ('cascade', 'face', 'hog', 'trackervit'))]
xml = Path(cv2.data.haarcascades) / 'haarcascade_frontalface_default.xml'
result = {
    'source_commit': '5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f',
    'source_path': str(SOURCE),
    'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'python': platform.python_version(), 'executable': sys.executable,
    'platform': platform.platform(), 'cv2_version': cv2.__version__,
    'cv2_path': cv2.__file__, 'packages': packages,
    'api': {n: hasattr(cv2, n) for n in (
        'CascadeClassifier', 'FaceDetectorYN', 'FaceDetectorYN_create',
        'FaceRecognizerSF', 'FaceRecognizerSF_create', 'QRCodeDetector',
        'TrackerVit', 'TrackerVit_create', 'dnn')},
    'cascade_names': [n for n in dir(cv2) if 'cascade' in n.lower()],
    'namespaces': namespaces,
    'haar_xml': {'path': str(xml), 'exists': xml.is_file(),
                 'bytes': xml.stat().st_size if xml.is_file() else None,
                 'sha256': hashlib.sha256(xml.read_bytes()).hexdigest() if xml.is_file() else None,
                 'data_directory_exists': xml.parent.is_dir(),
                 'data_directory_files': sorted(p.name for p in xml.parent.iterdir())},
    'yunet_cache': {'path': str(MODEL), 'bytes': MODEL.stat().st_size,
                    'sha256': PIN},
    'cases': [],
}
frames = {'black_320x240': np.zeros((240, 320, 3), np.uint8),
          'noise_320x240': np.random.default_rng(1234).integers(
              0, 256, (240, 320, 3), dtype=np.uint8)}
for cache_name, cache in [('unavailable', ROOT / 'empty-models'), ('verified', CACHE)]:
    assert cache.is_dir()
    if cache_name == 'unavailable':
        assert not list(cache.iterdir())
    app._model_dir = lambda cache=cache: str(cache)
    for optional in (False, True):
        logs = []
        callback = type('Callback', (), {'log': lambda self, msg: logs.append(msg)})()
        case = {'model_availability': cache_name,
                'optional_missing_model': optional, 'logs': logs}
        start = len(fetch_attempts)
        try:
            detector = app.FaceDetector(cb=callback, model_path=(
                str(ROOT / 'nonexistent-optional.onnx') if optional else None))
            case['constructor'] = 'ok'
            case['backend'] = 'yunet' if detector.yunet is not None else 'haar'
            case['haar_empty'] = detector.haar.empty() if detector.haar else None
            case['detections'] = {}
            for name, frame in frames.items():
                for scale in (1.0, 0.4):
                    detections = detector.find(frame, detect_scale=scale)
                    case['detections'][f'{name}_scale_{scale}'] = {
                        'count': len(detections),
                        'boxes': [[float(x) for x in box] for box in detections]}
        except Exception as exc:
            case['constructor' if 'constructor' not in case else 'detection'] = 'error'
            case['error'] = {'type': type(exc).__name__, 'message': str(exc),
                             'traceback': traceback.format_exc()}
        case['fetch_attempts'] = fetch_attempts[start:]
        result['cases'].append(case)
result['network_events'] = network_events
assert not list((ROOT / 'empty-models').iterdir())
assert hashlib.sha256(MODEL.read_bytes()).hexdigest() == PIN
print(json.dumps(result, indent=2))
