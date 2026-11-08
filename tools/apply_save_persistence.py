"""One-shot transport; removed before publishing the tested application source."""
from pathlib import Path
import base64
import hashlib
import lzma
import subprocess

assert subprocess.check_output(['git', 'hash-object', 'openscrub_web.py']).decode().strip() == 'c38338951483543f2940a68f59de86364e307fa5'
parts = [Path('tools/save_persistence_payload_%d.txt' % i) for i in range(3)]
encoded = ''.join(path.read_text().strip() for path in parts)
data = lzma.decompress(base64.b64decode(encoded, validate=True))
assert hashlib.sha256(data).hexdigest() == '45e26b7df9ff2c97b39c1072d481751799ed33889d4dcb631288a8960be6eac1'
subprocess.run(['git', 'apply', '--unidiff-zero', '--check', '-'], input=data, check=True)
subprocess.run(['git', 'apply', '--unidiff-zero', '-'], input=data, check=True)
for path in parts:
    path.unlink()
Path(__file__).unlink()
