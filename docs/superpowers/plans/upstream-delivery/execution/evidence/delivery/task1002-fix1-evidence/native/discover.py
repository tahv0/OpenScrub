import cv2,numpy as np,numpy._core._multiarray_umath as core,sys,json,hashlib
from pathlib import Path
def identify(path):
 p=Path(path).resolve();return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)
native=cv2._native
cap=cv2.VideoCapture('/tmp/openscrub-frame-identity-baseline-20261117/runtime/cfr5.mp4')
try:
 backend=dict(opened=cap.isOpened(),name=cap.getBackendName(),fps=cap.get(cv2.CAP_PROP_FPS),count=cap.get(cv2.CAP_PROP_FRAME_COUNT))
finally:cap.release()
print(json.dumps(dict(python=dict(executable=sys.executable,version=list(sys.version_info[:3])),opencv=dict(version=cv2.__version__,loader=identify(cv2.__file__),native=identify(native.__file__),build=cv2.getBuildInformation(),backend=backend),numpy=dict(version=np.__version__,loader=identify(np.__file__),multiarray_umath=identify(core.__file__)),scope='new prospective observations for repair gates; used extensions only, not transitive native certification'),indent=2))
