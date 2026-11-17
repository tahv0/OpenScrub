from pathlib import Path
import json
import sys
import numpy as np
import cv2
import python39_isolation

mode = sys.argv[1]
root = Path('/tmp/openscrub-python39-20261117')
web = python39_isolation.configure('api-' + mode)
import openscrub
location = Path(openscrub.__file__).resolve()
assert (root / ('source' if mode == 'source' else 'venv')).resolve() in location.parents
assert sys.version_info[:2] == (3, 9)
print(mode, sys.version.split()[0], location)

# Exercise native wheel imports with a small wholly synthetic image.
image = np.zeros((24, 32, 3), dtype=np.uint8)
image[6:18, 8:24] = (40, 120, 200)
ok, encoded = cv2.imencode('.png', image)
assert ok
decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
assert np.array_equal(decoded, image)
assert cv2.cvtColor(decoded, cv2.COLOR_BGR2GRAY).shape == (24, 32)
print('synthetic OpenCV/NumPy PNG roundtrip: 32x24 exact')

client = web.app.test_client()
response = client.get('/')
assert response.status_code == 200 and b'<script>' in response.data
assert 'no-store' in response.headers['Cache-Control']
print('GET / -> 200; UI present; no-store')
for endpoint in ('/api/jobs', '/api/models/face', '/api/model_status', '/api/vault'):
    response = client.get(endpoint)
    assert response.status_code == 200
    value = response.get_json()
    assert value is not None
    if endpoint == '/api/jobs':
        assert value == []
    print('GET', endpoint, '-> 200;', type(value).__name__)
response = client.post('/api/jobs', json={'server_path': str(root / 'runtime' / 'synthetic-missing.mp4')})
assert response.status_code == 400
print('POST /api/jobs synthetic missing path -> 400')
response = client.get('/zones')
assert response.status_code in (301, 302) and response.headers['Location'] == '/'
print('GET /zones -> redirect /')

try:
    openscrub._fetch_model('https://invalid.example/synthetic.onnx', str(root / 'runtime' / 'forbidden.onnx'))
except RuntimeError as exc:
    assert 'model downloads disabled' in str(exc)
    print('explicit outward model fetch blocked before networking')
else:
    raise AssertionError('model fetch was not blocked')
try:
    # Emit the same audit event directly: this sandbox denies socket creation
    # before connect, so a live external socket would test sandbox permissions.
    sys.audit('socket.connect', None, ('192.0.2.1', 443))
except RuntimeError as exc:
    assert 'outward network disabled' in str(exc)
    print('outward socket audit policy rejects external address')
else:
    raise AssertionError('outward socket was not blocked')
assert not list((root / 'runtime' / 'models').glob('*'))
print('no model files downloaded; API smoke passed')
